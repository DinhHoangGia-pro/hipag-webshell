import random

import pytest
import torch
from torch_geometric.loader import DataLoader

from hipag.data.synthetic import make_synthetic_dataset, make_synthetic_ir
from hipag.graph.edges import CAND, FUNC, IN_FUNC, PYG_EDGE, SEM_NEG, SEM_POS, STMT, STORED_EDGE_TYPES
from hipag.graph.hierarchical_graph import build_hetero_from_ir
from hipag.graph.node_features import NODE_FEAT_DIM, global_features, shannon_entropy, token_ids
from hipag.graph.taint_seeds import classify_token, primary_role, reachable_within
from hipag.model.taint_predictor import build_seed_pairs


def test_taint_seeds():
    assert classify_token("$_GET") == "source" and classify_token("EVAL") == "sink"
    assert classify_token("base64_decode") == "decode" and classify_token("strlen") is None
    assert primary_role(["eval", "$_POST"], {"eval"}) == "sink"     # quy ước sink > source (eval là construct)
    assert primary_role(["eval", "$_POST"]) == "source"             # luật call node: không có construct -> không sink


def test_reachable_within_hops():
    r = reachable_within([(0, 1), (1, 2), (2, 3)], 4, max_hops=2)
    assert r(0, 2) and not r(0, 3) and not r(2, 0) and not r(1, 1)


def test_entropy_and_tokens():
    assert shannon_entropy("") == 0.0 and shannon_entropy("aaaa") == 0.0
    assert shannon_entropy("ab") == pytest.approx(1.0)
    ids = token_ids(["eval", "$x"], 4096, 5)
    assert len(ids) == 5 and ids[2:] == [0, 0, 0] and all(0 < i < 4096 for i in ids[:2])
    assert token_ids(["EVAL"], 4096, 1) == token_ids(["eval"], 4096, 1)   # ổn định, không phân biệt hoa thường
    g = global_features("<?php eval(base64_decode($x)); $f($y);")
    assert g[1:] == [1.0, 1.0, 1.0]


def test_seed_pairs_hard_negatives():
    roles = ["source", None, "sink", None, "sink"]
    reach = reachable_within([(0, 1), (1, 2), (2, 3), (3, 4)], 5, 8)
    cand = [(i, j) for i in range(5) for j in reach.reach_set(i)]
    pos, neg = build_seed_pairs(roles, reach, neg_per_pos=2, seed=0, candidates=cand, hard_frac=1.0)
    assert set(map(tuple, pos.t().tolist())) == {(0, 2), (0, 4)}
    negs = set(map(tuple, neg.t().tolist()))
    assert len(negs) == 4 and not negs & {(0, 2), (0, 4)} and negs <= set(cand)


def _check_graph(d):
    S, F = d[STMT].num_nodes, d[FUNC].num_nodes
    assert d[STMT].x.shape == (S, NODE_FEAT_DIM) and d[STMT].x_tok.shape[0] == S
    for et in STORED_EDGE_TYPES:
        ei = d[et].edge_index
        assert ei.dtype == torch.long and ei.shape[0] == 2
        if ei.numel():
            assert ei[0].max() < (S if et[0] == STMT else F)
            assert ei[1].max() < (S if et[2] == STMT else F)
    assert d[IN_FUNC].edge_index.shape[1] == S          # mỗi stmt thuộc đúng 1 function
    role = d[STMT].role
    pos = d[SEM_POS].edge_index
    assert bool((role[pos[0]] == 1).all() and (role[pos[1]] == 2).all())   # positive = source->sink
    cand = set(map(tuple, d[CAND].edge_index.t().tolist()))
    assert set(map(tuple, pos.t().tolist())) <= cand                       # positive ⊆ ứng viên (chưa bị cap)
    assert not set(map(tuple, pos.t().tolist())) & set(map(tuple, d[SEM_NEG].edge_index.t().tolist()))


def test_build_from_ir_and_webshell_has_positive():
    rng = random.Random(1)
    n_with_pos = 0
    for k in range(40):
        d = build_hetero_from_ir(make_synthetic_ir(rng, 1), label=1, seed=k)
        _check_graph(d)
        n_with_pos += d[SEM_POS].edge_index.shape[1] > 0
    assert n_with_pos >= 20     # ~75% webshell giả có luồng source->sink tách statement


def test_empty_file_and_caps():
    d = build_hetero_from_ir({"functions": [], "source_text": ""}, label=0)
    assert d[STMT].num_nodes == 1 and d[FUNC].num_nodes == 1
    big = {"functions": [{"stmts": [{"kind": "Echo", "text": "x", "tokens": ["x"]}] * 300,
                          "cfg": [], "dfg": []}] * 60}
    d = build_hetero_from_ir(big, {"max_stmt_per_block": 10, "max_func_per_file": 3,
                                   "taint": {"max_cand": 7}})
    assert d[STMT].num_nodes == 30 and d[FUNC].num_nodes == 3 and d[CAND].edge_index.shape[1] == 7


def test_batching_offsets():
    ds = make_synthetic_dataset(6, seed=3)
    b = next(iter(DataLoader(ds, batch_size=6)))
    assert b.y.shape == (6,) and b.global_x.shape == (6, 4)
    assert b[FUNC].batch.shape[0] == b[FUNC].num_nodes == sum(d[FUNC].num_nodes for d in ds)
    _check_graph(b)                                       # chỉ số cạnh đã được dịch đúng khi gộp batch
    assert b[PYG_EDGE["E_seq"]].edge_index.shape[1] == sum(d[PYG_EDGE["E_seq"]].edge_index.shape[1] for d in ds)
