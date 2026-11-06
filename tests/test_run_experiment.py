"""Smoke test end-to-end harness trên dữ liệu giả (CPU, epoch ít)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path, *extra):
    cmd = [sys.executable, str(ROOT / "scripts/run_experiment.py"), "--config", "configs/experiment/rq4_ablation.yaml",
           "--synthetic", "--epochs", "1", "--device", "cpu", "--out", str(tmp_path / "run"), *extra]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)


def test_harness_synthetic_ablation(tmp_path):
    tex = tmp_path / "numbers.tex"
    p = _run(tmp_path, "--seeds", "2", "--variants", "full", "no_e_sem", "--numbers-tex", str(tex))
    assert p.returncode == 0, p.stderr[-3000:]
    s = json.loads((tmp_path / "run/summary.json").read_text())
    assert set(s) == {"full", "no_e_sem"}
    assert len(s["full"]["test"]["f1_macro"]) == 2            # (mean, sd)
    assert "prec_at_base_0p1pct" in s["full"]["test"]
    assert "KHÔNG dùng cho paper" in (tmp_path / "run/summary.md").read_text()
    assert not tex.exists()                                    # dữ liệu giả không bao giờ ghi numbers.tex
    led = json.loads((tmp_path / "run/ledger.json").read_text())
    assert led["seeds"] == [0, 1] and led["torch"]
    # chạy lại: seed đã xong được bỏ qua (resume mức seed)
    p2 = _run(tmp_path, "--seeds", "2", "--variants", "full")
    assert p2.returncode == 0 and p2.stdout.count("đã có, bỏ qua") == 2


def test_harness_rejects_unknown_variant(tmp_path):
    p = _run(tmp_path, "--seeds", "1", "--variants", "bogus")
    assert p.returncode != 0 and "không hỗ trợ" in p.stderr
