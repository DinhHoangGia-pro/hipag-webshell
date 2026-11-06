import pytest
import torch
import yaml
from torch_geometric.loader import DataLoader

from hipag.data.synthetic import make_synthetic_dataset
from hipag.graph.hierarchical_graph import build_hetero_from_ir
from hipag.model.hipag import ABLATIONS, HiPaG
from hipag.model.taint_predictor import TaintDependencyPredictor, calibrate_tau
from hipag.model.token_transformer import TokenSequenceTransformer


def small_cfg(ablation="full"):
    with open("configs/model/hipag_base.yaml") as f:
        cfg = yaml.safe_load(f)
    m = cfg["model"]
    m["token_transformer"].update(d_embed=16, heads=2, layers=1)
    m["intra_gatv2"].update(hidden=32)
    m["inter_transformer"].update(hidden=32)
    m["taint_predictor"].update(mlp_hidden=16)
    m["ablation"] = ablation
    return cfg


@pytest.fixture(scope="module")
def batch():
    return next(iter(DataLoader(make_synthetic_dataset(8, seed=0), batch_size=8)))


@pytest.mark.parametrize("abl", ABLATIONS)
def test_forward_all_ablations(batch, abl):
    torch.manual_seed(0)
    model = HiPaG(small_cfg(abl))
    out = model(batch)
    assert out["logit"].shape == (8,) and torch.isfinite(out["logit"]).all()
    assert torch.isfinite(out["taint_loss"])
    loss = torch.nn.functional.binary_cross_entropy_with_logits(out["logit"], batch.y) + out["taint_loss"]
    loss.backward()
    if abl == "no_e_sem":
        assert out["n_sem"] == 0 and out["taint_loss"].item() == 0.0


def test_detection_loss_reaches_taint_predictor(batch):
    torch.manual_seed(0)
    model = HiPaG(small_cfg())
    model.taint.tau = 0.0              # giữ mọi ứng viên để chắc có cạnh E_sem
    out = model(batch)
    assert out["n_sem"] > 0
    torch.nn.functional.binary_cross_entropy_with_logits(out["logit"], batch.y).backward()   # KHÔNG cộng taint_loss
    g = model.taint.mlp[0].weight.grad
    assert g is not None and g.abs().sum() > 0


def test_single_graph_and_empty_function():
    ir = {"functions": [{"stmts": [{"kind": "Echo", "text": "", "tokens": []}]},   # statement rỗng (toàn PAD)
                        {"stmts": []}],                                            # function không statement
          "calls": [(0, 1)], "source_text": ""}
    d = build_hetero_from_ir(ir, label=0)
    model = HiPaG(small_cfg()).eval()
    out = model(d)
    assert out["logit"].shape == (1,) and torch.isfinite(out["logit"]).all()


def test_token_transformer_static_vs_ctx():
    x = torch.tensor([[5, 6, 0], [0, 0, 0]])
    for enc in (True, False):
        y = TokenSequenceTransformer(100, 8, 2, 1, max_len=3, use_encoder=enc)(x)
        assert y.shape == (2, 8) and torch.isfinite(y).all()


def test_predictor_learns_and_calibrates():
    torch.manual_seed(0)
    h = torch.randn(20, 8)
    pos = torch.tensor([[0, 1, 2], [3, 4, 5]]); neg = torch.tensor([[6, 7, 8, 9], [10, 11, 12, 13]])
    tp = TaintDependencyPredictor(8, 16, dropout=0.0)
    opt = torch.optim.Adam(tp.parameters(), 1e-2)
    for _ in range(200):
        opt.zero_grad(); tp.bce_loss(h, pos, neg).backward(); opt.step()
    p = torch.sigmoid(tp(h, torch.cat([pos, neg], 1)))
    lab = torch.tensor([1.0] * 3 + [0.0] * 4)
    tau = calibrate_tau(p, lab)
    assert ((p > tau).float() == lab).all()
    kept, _ = tp.predict_edges(h, torch.cat([pos, neg], 1), tau)
    assert kept.shape[1] == 3
