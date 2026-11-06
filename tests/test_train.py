import csv
import math

import torch

from hipag.data.dataset import WebshellGraphDataset
from hipag.data.synthetic import make_synthetic_dataset
from hipag.train import train_one_seed
from test_model import small_cfg


def _cfg(epochs=6):
    cfg = small_cfg()
    cfg["train"].update(epochs=epochs, batch_size=16, lr=3e-3, patience=50)
    return cfg


def test_dataset_reads_split_csv(tmp_path):
    feats = tmp_path / "features"; feats.mkdir()
    graphs = make_synthetic_dataset(5, seed=9)
    rows = []
    for k, g in enumerate(graphs):
        torch.save(g, feats / f"s{k}.pt")
        rows.append({"sample_id": f"s{k}", "path": f"s{k}.pt", "label": int(g.y.item()),
                     "split": "train" if k < 3 else "test", "level": "L0"})
    rows.append({"sample_id": "gone", "path": "gone.pt", "label": 1, "split": "train", "level": "L0"})
    max_ok = max((feats / f"s{k}.pt").stat().st_size for k in range(5))
    (feats / "big.pt").write_bytes(b"x" * (max_ok + 1))
    rows.append({"sample_id": "big", "path": "big.pt", "label": 0, "split": "train", "level": "L0"})
    csv_p = tmp_path / "splits.csv"
    with open(csv_p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    ds = WebshellGraphDataset(str(csv_p), str(feats), split="train", max_bytes=max_ok)
    assert len(ds) == 3 and set(ds.skipped) == {("gone", "missing"), ("big", "too_large")}
    assert ds[0].y.item() == graphs[0].y.item()
    assert len(WebshellGraphDataset(str(csv_p), str(feats), where={"level": "L1"})) == 0


def test_train_one_seed_learns_synthetic():
    tr, va, te = make_synthetic_dataset(96, 1), make_synthetic_dataset(48, 2), make_synthetic_dataset(48, 3)
    r = train_one_seed(_cfg(8), 0, tr, va, {"test": te}, "cpu", log=lambda *_: None)
    m = r["test"]["test"]
    assert m["roc_auc"] > 0.8, m                    # dữ liệu giả có tín hiệu rõ -> phải học được
    assert 0.0 <= r["val"]["taint_tau"] <= 1.0 and "taint_edge_f1" in m
    assert len(r["scores"]["test"]["score"]) == 48 and 0 <= r["best_epoch"] < 8


def test_seed_reproducible_and_resume(tmp_path):
    tr, va, te = make_synthetic_dataset(32, 1), make_synthetic_dataset(16, 2), make_synthetic_dataset(16, 3)
    quiet = lambda *_: None  # noqa: E731
    a = train_one_seed(_cfg(3), 7, tr, va, {"test": te}, "cpu", log=quiet)
    b = train_one_seed(_cfg(3), 7, tr, va, {"test": te}, "cpu", log=quiet)
    assert a["scores"]["test"]["score"] == b["scores"]["test"]["score"]
    # resume: chạy 2 epoch -> "dừng" -> chạy tiếp tới 3 epoch; lịch sử nối tiếp đủ 3 epoch
    out = tmp_path / "ck"
    train_one_seed(_cfg(2), 7, tr, va, {"test": te}, "cpu", out_dir=str(out), log=quiet)
    logs = []
    c = train_one_seed(_cfg(3), 7, tr, va, {"test": te}, "cpu", out_dir=str(out), log=logs.append)
    assert any("resume từ epoch 2" in s for s in logs)
    assert [h["epoch"] for h in c["history"]] == [0, 1, 2] and (out / "best.pt").exists()
    assert not math.isnan(c["test"]["test"]["f1_macro"])
