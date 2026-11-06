"""Lắp đồ thị phân cấp statement->function->file thành PyG HeteroData.

Hai bước tách rời:
  1. PHP --(parsing/)--> IR  (TODO Bước 13–14: AST nikic -> IR; chưa làm trong phiên này)
  2. IR  --build_hetero_from_ir--> HeteroData   (đã làm; dữ liệu giả cũng đi qua đây)

IR (dict, chỉ số statement là CỤC BỘ trong hàm):
    {
      "functions": [ {"name": str,
                      "stmts": [{"kind": str, "text": str, "tokens": [str]}, ...],
                      "cfg": [(i, j), ...], "dfg": [(i, j), ...]}, ... ],   # functions[0] = phạm vi file
      "calls":    [(f_src, f_dst), ...],      # chỉ số function
      "includes": [(f_src, f_dst), ...],
      "source_text": str,
    }

HeteroData đầu ra:
    stmt.x [S, NODE_FEAT_DIM] float, stmt.x_tok [S, L] long (0=PAD), stmt.role [S] long (0 none,1 src,2 sink,3 dec)
    func.num_nodes = F
    edges: seq, skip, cfg, dfg, cand, sem_pos, sem_neg (stmt->stmt); in (stmt->func); call, include (func->func)
    global_x [1, GLOBAL_FEAT_DIM], y [1] float (nếu có nhãn)
    n_cand_full [1] long (số ứng viên trước cap), cand_capped [1] bool (max_cand có cắt không)
"""
from __future__ import annotations

import random

import torch
from torch_geometric.data import HeteroData

from ..model.taint_predictor import build_seed_pairs
from .edges import CAND, FUNC, IN_FUNC, PYG_EDGE, SEM_NEG, SEM_POS, STMT
from .node_features import global_features, node_vector, token_ids
from .taint_seeds import primary_role, reachable_within

ROLE_ID = {None: 0, "source": 1, "sink": 2, "decode": 3}

DEFAULT_GRAPH_CFG = {
    "skip_window_delta": 2,     # E_skip: i -> i+2..i+δ
    "max_stmt_per_block": 200,  # cắt statement mỗi function
    "max_func_per_file": 50,
    "vocab_size": 4096,
    "max_tok_len": 32,
    "taint": {
        "max_hops": 8,          # cửa sổ CFG∪DFG∪E_seq cho cặp ứng viên/positive
        "neg_per_pos": 5,
        "max_pos": 4096,
        "max_cand": 4096,       # cap số cặp ứng viên E_sem mỗi file (lấy mẫu ngẫu nhiên, KHÔNG theo vai trò)
        "hard_frac": 0.5,
    },
}


def _cfg(cfg: dict | None) -> dict:
    from ..utils.config import deep_merge
    return deep_merge(DEFAULT_GRAPH_CFG, cfg or {})


def _et(pairs) -> torch.Tensor:
    return (torch.tensor(pairs, dtype=torch.long).t().contiguous()
            if pairs else torch.empty(2, 0, dtype=torch.long))


def build_hetero_from_ir(ir: dict, cfg: dict | None = None, label: int | None = None, seed: int = 0) -> HeteroData:
    cfg = _cfg(cfg)
    tcfg = cfg["taint"]
    max_s, delta = cfg["max_stmt_per_block"], cfg["skip_window_delta"]

    funcs = list(ir.get("functions", []))[: cfg["max_func_per_file"]] or [{"name": "<main>", "stmts": []}]
    xs, toks, roles, in_func = [], [], [], []
    seq, skip, cfg_e, dfg_e = [], [], [], []
    for f_id, fn in enumerate(funcs):
        stmts = fn.get("stmts", [])[:max_s]
        if f_id == 0 and not stmts and len(funcs) == 1:
            stmts = [{"kind": "Nop", "text": "", "tokens": []}]   # file rỗng: giữ 1 nút để batch không vỡ
        off, n = len(xs), len(stmts)
        for p, st in enumerate(stmts):
            xs.append(node_vector(st, p, n))
            toks.append(token_ids(st.get("tokens", []), cfg["vocab_size"], cfg["max_tok_len"]))
            roles.append(primary_role(st.get("tokens", [])))
            in_func.append((off + p, f_id))
        seq += [(off + i, off + i + 1) for i in range(n - 1)]
        skip += [(off + i, off + i + d) for d in range(2, delta + 1) for i in range(n - d)]
        for src_list, dst in ((fn.get("cfg", []), cfg_e), (fn.get("dfg", []), dfg_e)):
            dst += [(off + i, off + j) for i, j in src_list if 0 <= i < n and 0 <= j < n and i != j]

    S, F = len(xs), len(funcs)
    # Cặp ứng viên E_sem: j tới được từ i trong cửa sổ (cạnh đều trong-hàm -> ứng viên trong-hàm)
    reach = reachable_within(seq + cfg_e + dfg_e, S, tcfg["max_hops"])
    cand = [(i, j) for i in range(S) for j in sorted(reach.reach_set(i))]
    rng = random.Random(seed)
    n_cand_full = len(cand)
    if len(cand) > tcfg["max_cand"]:
        cand = rng.sample(cand, tcfg["max_cand"])
    pos, neg = build_seed_pairs(roles, reach, neg_per_pos=tcfg["neg_per_pos"], max_pos=tcfg["max_pos"],
                                seed=seed, candidates=cand, hard_frac=tcfg["hard_frac"])

    calls = [(a, b) for a, b in ir.get("calls", []) if a < F and b < F]
    incs = [(a, b) for a, b in ir.get("includes", []) if a < F and b < F]

    d = HeteroData()
    d[STMT].x = torch.tensor(xs, dtype=torch.float)
    d[STMT].x_tok = torch.tensor(toks, dtype=torch.long)
    d[STMT].role = torch.tensor([ROLE_ID[r] for r in roles], dtype=torch.long)
    d[FUNC].num_nodes = F
    d[PYG_EDGE["E_seq"]].edge_index = _et(seq)
    d[PYG_EDGE["E_skip"]].edge_index = _et(skip)
    d[PYG_EDGE["E_cfg"]].edge_index = _et(cfg_e)
    d[PYG_EDGE["E_dfg"]].edge_index = _et(dfg_e)
    d[PYG_EDGE["E_call"]].edge_index = _et(calls)
    d[PYG_EDGE["E_include"]].edge_index = _et(incs)
    d[CAND].edge_index = _et(cand)
    d[SEM_POS].edge_index = pos
    d[SEM_NEG].edge_index = neg
    d[IN_FUNC].edge_index = _et(in_func)
    d.n_cand_full = torch.tensor([n_cand_full])                       # trước khi cap
    d.cand_capped = torch.tensor([n_cand_full > tcfg["max_cand"]])    # max_cand có binding không
    d.global_x = torch.tensor([global_features(ir.get("source_text", ""))], dtype=torch.float)
    if label is not None:
        d.y = torch.tensor([float(label)])
    return d


def build_hierarchical_graph(php_file: str, cfg):
    """PHP file -> HeteroData. Cần bước AST->IR (Bước 13–14) — CHƯA làm trong phiên này."""
    raise NotImplementedError("TODO(Bước 13–14): parsing.php_ast.dump_ast -> ast_to_ir -> build_hetero_from_ir")
