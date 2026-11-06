"""Đóng Bước 5: rule_e_sem cùng vũ trụ ứng viên, log max_cand, cờ direct_source_sink, sweep RQ5."""
import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest
import torch
from torch_geometric.loader import DataLoader

from hipag.data.synthetic import make_synthetic_ir
from hipag.graph.edges import CAND, SEM_POS, STMT
from hipag.graph.hierarchical_graph import build_hetero_from_ir
from hipag.graph.node_features import NODE_FEAT_DIM, N_NUMERIC, node_vector
from hipag.model.hipag import HiPaG
from hipag.utils.config import load_config
from test_model import small_cfg

ROOT = Path(__file__).resolve().parents[1]
pairs = lambda ei: set(map(tuple, ei.t().tolist()))  # noqa: E731


def _webshell_batch(max_cand, n=24, seed=0):
    """Batch webshell giả có luồng source->sink; max_cand điều khiển việc cắt ứng viên."""
    rng = random.Random(seed)
    graphs = [build_hetero_from_ir(make_synthetic_ir(rng, 1), {"taint": {"max_cand": max_cand}}, label=1, seed=k)
              for k in range(n)]
    return next(iter(DataLoader(graphs, batch_size=n)))


def test_rule_edges_subset_of_candidates_when_max_cand_binds():
    b = _webshell_batch(max_cand=3)
    assert torch.equal(b.cand_capped, b.n_cand_full > 3)         # cờ khớp đúng định nghĩa binding
    assert b.cand_capped.float().mean() > 0.5                    # đa số đồ thị bị cắt
    rule, cand, seed = pairs(HiPaG.rule_edges(b)), pairs(b[CAND].edge_index), pairs(b[SEM_POS].edge_index)
    assert rule <= cand and rule <= seed
    assert len(rule) < len(seed)                                 # cap thật sự loại bớt cạnh luật


def test_rule_edges_equal_seed_reachable_when_not_binding():
    b = _webshell_batch(max_cand=10**6)
    assert not b.cand_capped.any()
    seed = pairs(b[SEM_POS].edge_index)
    assert len(seed) > 0 and pairs(HiPaG.rule_edges(b)) == seed
    cfg = small_cfg("rule_e_sem")
    cfg["model"]["taint_predictor"]["top_k"] = 0                 # tắt top-k để so nguyên tập
    out = HiPaG(cfg)(b)
    assert pairs(out["sem_ei"]) == seed


def test_cand_capped_frac_logged():
    rng = random.Random(1)
    gs = [build_hetero_from_ir(make_synthetic_ir(rng, 1), {"taint": {"max_cand": mc}}, label=1, seed=k)
          for k, mc in enumerate([3, 3, 10**6, 10**6])]
    out = HiPaG(small_cfg())(next(iter(DataLoader(gs, batch_size=4))))
    assert out["cand_capped_frac"] == pytest.approx(0.5)


def test_direct_source_sink_flag():
    idx = NODE_FEAT_DIM - N_NUMERIC - 1
    v = lambda toks: node_vector({"kind": "Eval", "text": " ".join(toks), "tokens": toks})[idx]  # noqa: E731
    assert v(["eval", "$_POST", "'c'"]) == 1.0
    assert v(["eval", "$x"]) == 0.0 and v(["$x", "=", "$_GET"]) == 0.0
    assert v(["system", "base64_decode", "$_COOKIE"]) == 1.0


def _harness():
    spec = importlib.util.spec_from_file_location("run_experiment", ROOT / "scripts/run_experiment.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_rq5_config_and_sweep_expansion():
    cfg = load_config(ROOT / "configs/experiment/rq5_taint_hparams.yaml", root=ROOT)
    tp = cfg["model"]["taint_predictor"]
    assert tp["tau_floor"] == 0.3 and tp["mlp_hidden"] == 128 and tp["pos_weight"] == "auto"   # kế thừa base
    assert cfg["select"] == {"split": "val", "metric": "f1_macro"} and cfg["eval_sets"] == {}
    h = _harness()
    pts = h.expand_sweep(cfg["sweep"])
    assert len(pts) == 9 and pts[0] == ("top_k4_warmup_epochs3",
                                        {"model.taint_predictor.top_k": 4, "model.taint_predictor.warmup_epochs": 3})
    with pytest.raises(SystemExit):
        h.set_by_path(cfg, "model.taint_predictor.topk", 4)      # gõ sai khoá -> lỗi, không âm thầm bỏ qua


def test_rq5_sweep_harness_synthetic(tmp_path):
    cmd = [sys.executable, str(ROOT / "scripts/run_experiment.py"), "--config",
           "configs/experiment/rq5_taint_hparams.yaml", "--synthetic", "--epochs", "4", "--device", "cpu",
           "--seeds", "1", "--variants", "top_k4_warmup_epochs3", "top_k16_warmup_epochs3", "--out", str(tmp_path)]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, p.stderr[-3000:]
    best = json.loads((tmp_path / "sweep_best.json").read_text())
    assert best["best"] in {"top_k4_warmup_epochs3", "top_k16_warmup_epochs3"} and len(best["ranking"]) == 2
    s = json.loads((tmp_path / "summary.json").read_text())
    assert set(s["top_k4_warmup_epochs3"]) == {"val"}                 # không đánh giá test khi chọn siêu tham số
    led = json.loads((tmp_path / "ledger.json").read_text())
    assert led["config"]["model"]["taint_predictor"]["tau_floor"] == 0.3
    r = json.loads((tmp_path / "top_k16_warmup_epochs3/seed_0.json").read_text())
    assert [h["sem_mode"] for h in r["history"]] == ["rule"] * 3 + ["learned"]   # warmup_epochs=3 được áp
    assert "cand_capped_frac" in r["history"][0]
    assert "KHÔNG ghi numbers.tex" in p.stdout
