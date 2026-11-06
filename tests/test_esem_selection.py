"""Chọn cạnh E_sem: top-k mỗi sink, sàn tau, warmup luật -> học được."""
from collections import Counter

import pytest
import torch
from torch_geometric.loader import DataLoader

from hipag.data.synthetic import make_synthetic_dataset
from hipag.graph.edges import CAND, SEM_POS
from hipag.model.hipag import HiPaG
from hipag.model.taint_predictor import TaintDependencyPredictor, calibrate_tau, topk_per_dst
from hipag.train import train_one_seed
from test_model import small_cfg


@pytest.mark.parametrize("k", [1, 3, 8])
def test_topk_per_dst_exact(k):
    g = torch.Generator().manual_seed(k)
    dst = torch.randint(0, 20, (500,), generator=g)
    score = torch.rand(500, generator=g)
    keep = topk_per_dst(dst, score, k)
    for d in dst.unique().tolist():
        grp = dst == d
        n_keep = int((keep & grp).sum())
        assert n_keep == min(k, int(grp.sum()))                       # đúng min(k, |nhóm|) cạnh mỗi sink
        if (grp & ~keep).any():
            assert score[keep & grp].min() >= score[grp & ~keep].max()   # giữ đúng các cạnh điểm cao nhất


def test_topk_disabled_and_ties_deterministic():
    dst = torch.tensor([0, 0, 0, 1])
    assert topk_per_dst(dst, torch.rand(4), None).all() and topk_per_dst(dst, torch.rand(4), 0).all()
    assert topk_per_dst(dst, torch.ones(4), 2).tolist() == [True, True, False, True]   # hoà -> chỉ số nhỏ trước


def test_tau_floor():
    tp = TaintDependencyPredictor(4, 8, tau=0.0, tau_floor=0.3, top_k=None)
    assert tp.effective_tau == 0.3
    pairs = torch.tensor([[0, 1, 2, 3], [5, 5, 5, 5]])
    p = torch.tensor([0.1, 0.29, 0.31, 0.9])
    assert tp.select_edges(pairs, p).tolist() == [False, False, True, True]
    # calibrate không trả tau dưới sàn dù F1 tốt nhất nằm dưới sàn
    probs = torch.tensor([0.2, 0.25, 0.05, 0.01]); lab = torch.tensor([1.0, 1.0, 0.0, 0.0])
    assert calibrate_tau(probs, lab) < 0.2 and calibrate_tau(probs, lab, tau_floor=0.3) >= 0.3


@pytest.fixture(scope="module")
def batch():
    return next(iter(DataLoader(make_synthetic_dataset(16, seed=5), batch_size=16)))


def test_model_learned_edges_capped_per_sink(batch):
    cfg = small_cfg()
    cfg["model"]["taint_predictor"].update(top_k=2, tau_floor=0.0)
    torch.manual_seed(0)
    model = HiPaG(cfg)
    model.taint.tau = 0.0                         # tình huống xấu nhất: ngưỡng không lọc gì
    out = model(batch)
    per_sink = Counter(out["sem_ei"][1].tolist())
    assert out["n_sem"] > 0 and max(per_sink.values()) <= 2
    assert out["n_sem"] <= 2 * batch[CAND].edge_index[1].unique().numel()
    assert out["n_sem"] < batch[CAND].edge_index.shape[1]       # không còn "giữ gần hết ứng viên"


def test_warmup_rule_then_learned(batch):
    cfg = small_cfg()
    cfg["model"]["taint_predictor"].update(warmup_epochs=2, top_k=8)
    model = HiPaG(cfg)
    assert [model.set_epoch(e) for e in range(4)] == ["rule", "rule", "learned", "learned"]
    model.set_epoch(0)
    out = model(batch)
    rule = set(map(tuple, batch[SEM_POS].edge_index.t().tolist()))
    assert set(map(tuple, out["sem_ei"].t().tolist())) <= rule            # warmup: chỉ cạnh luật
    assert out["taint_loss"].item() > 0                                   # predictor vẫn học khi warmup
    cfg["model"]["ablation"] = "no_e_sem"
    assert HiPaG(cfg).set_epoch(0) == "none"                              # ablation không bị warmup ghi đè


def test_train_with_warmup_selects_learned_checkpoint():
    cfg = small_cfg()
    cfg["model"]["taint_predictor"].update(warmup_epochs=2)
    cfg["train"].update(epochs=4, batch_size=16, lr=3e-3, patience=1)   # patience nhỏ: không được dừng trong warmup
    tr, va, te = make_synthetic_dataset(32, 1), make_synthetic_dataset(16, 2), make_synthetic_dataset(16, 3)
    r = train_one_seed(cfg, 0, tr, va, {"test": te}, "cpu", log=lambda *_: None)
    modes = [h["sem_mode"] for h in r["history"]]
    assert modes[:3] == ["rule", "rule", "learned"]
    assert r["sem_mode"] == "learned" and r["best_epoch"] >= 2
    assert all(h["tau"] is None or h["tau"] >= 0.3 for h in r["history"])


def test_esem_does_not_collapse_after_warmup():
    """Hồi quy: không cân bằng BCE cạnh -> p(pos) co về ~1/6 < tau_floor -> E_sem = 0 sau vài epoch."""
    cfg = small_cfg()
    cfg["model"]["taint_predictor"].update(warmup_epochs=1)
    cfg["train"].update(epochs=8, batch_size=16, lr=3e-3, patience=50)
    tr, va, te = make_synthetic_dataset(64, 1), make_synthetic_dataset(32, 2), make_synthetic_dataset(16, 3)
    r = train_one_seed(cfg, 0, tr, va, {"test": te}, "cpu", log=lambda *_: None)
    learned = [h["n_sem_val"] for h in r["history"] if h["sem_mode"] == "learned"]
    assert min(learned[-3:]) > 0, learned
    assert r["val"]["taint_edge_f1"] > 0
