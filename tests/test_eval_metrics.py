import math

import numpy as np
import pytest

from hipag.eval import base_rate_precision, evaluate, fpr_at_tpr, tex_macro_name, write_numbers_tex
from hipag.utils.config import deep_merge
from hipag.utils.metrics import aggregate_seeds, format_mean_sd


def test_evaluate_perfect():
    y = [0, 0, 1, 1]
    r = evaluate(y, [0.1, 0.2, 0.8, 0.9])
    assert r["f1_macro"] == 1.0 and r["mcc"] == 1.0 and r["pr_auc"] == 1.0
    assert r["fpr_at_tpr95"] == 0.0
    assert r["prec_at_base_0p1pct"] == 1.0   # fpr=0 -> precision 1 ở mọi base-rate


def test_base_rate_formula_by_hand():
    # 10 âm, 10 dương. Dương đều 0.9; âm: 2 cái 0.95 (FP), 8 cái 0.1 -> tại TPR=1: FPR=0.2
    y = [1] * 10 + [0] * 10
    s = [0.9] * 10 + [0.95, 0.95] + [0.1] * 8
    assert fpr_at_tpr(y, s) == pytest.approx(0.2)
    bp = base_rate_precision(y, s, prevalences=(0.1, 0.01))
    assert bp[0.1] == pytest.approx(0.1 / (0.1 + 0.2 * 0.9))
    assert bp[0.01] == pytest.approx(0.01 / (0.01 + 0.2 * 0.99))


def test_single_class_gives_nan_not_crash():
    r = evaluate([1, 1, 1], [0.2, 0.7, 0.9])
    assert math.isnan(r["pr_auc"]) and math.isnan(r["fpr_at_tpr95"])
    assert r["recall"] == pytest.approx(2 / 3)


def test_aggregate_seeds_mean_sd_and_nan():
    per = [{"f1_macro": 0.8, "pr_auc": math.nan, "y": [1, 2]},
           {"f1_macro": 0.9, "pr_auc": 0.5},
           {"f1_macro": 1.0, "pr_auc": 0.7}]
    agg = aggregate_seeds(per)
    assert "y" not in agg
    m, sd = agg["f1_macro"]
    assert m == pytest.approx(0.9) and sd == pytest.approx(np.std([0.8, 0.9, 1.0], ddof=1))
    assert agg["pr_auc"][0] == pytest.approx(0.6)
    assert math.isnan(aggregate_seeds([{"a": 1.0}])["a"][1])
    assert format_mean_sd(0.9, 0.01) == "90.00 ± 1.00"


def test_tex_macro_name():
    assert tex_macro_name("HiPaG", "f1_macro") == "HiPaGFOneMacro"
    assert tex_macro_name("RqFour", "no_e_sem", "prec_at_base_0p1pct") == "RqFourNoESemPrecAtBaseZeroPOnePct"


def test_write_numbers_tex_merges(tmp_path):
    p = tmp_path / "numbers.tex"
    p.write_text("% header\n\\newcommand{\\Other}{42}\n")
    write_numbers_tex({"f1_macro": (0.9, 0.01), "mcc": (0.8, 0.02)}, str(p), n_seeds=5)
    write_numbers_tex({"f1_macro": (0.95, 0.005)}, str(p))   # ghi đè macro trùng tên
    txt = p.read_text()
    assert "\\newcommand{\\Other}{42}" in txt
    assert txt.count("\\HiPaGFOneMacro}") == 1 and "95.00 \\pm 0.50" in txt
    assert "0.800 \\pm 0.020" in txt   # MCC không nhân 100


def test_deep_merge():
    assert deep_merge({"a": {"x": 1, "y": 2}}, {"a": {"y": 3}}) == {"a": {"x": 1, "y": 3}}
