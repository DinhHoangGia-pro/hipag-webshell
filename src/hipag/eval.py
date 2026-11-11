"""Metrics chuẩn nhóm: F1_macro, acc, precision, recall, MCC, PR-AUC, FPR@TPR95,
+ base-rate precision @ {10%,1%,0.1%} (RQF-07). Xuất macro vào paper/numbers.tex.

Quy ước: lớp dương (1) = webshell; y_score = P(webshell) ∈ [0,1].
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from sklearn.metrics import (accuracy_score, average_precision_score, f1_score,
                             matthews_corrcoef, precision_score, recall_score,
                             roc_auc_score, roc_curve)


def _two_classes(y_true) -> bool:
    return len(np.unique(y_true)) == 2


def operating_point_at_tpr(y_true, y_score, target_tpr: float = 0.95) -> tuple[float, float, float]:
    """Điểm ROC đầu tiên đạt TPR ≥ target. Trả (fpr, tpr, threshold); nan nếu chỉ có 1 lớp."""
    y_true = np.asarray(y_true); y_score = np.asarray(y_score)
    if not _two_classes(y_true):
        return math.nan, math.nan, math.nan
    fpr, tpr, thr = roc_curve(y_true, y_score)
    idx = int(np.argmax(tpr >= target_tpr - 1e-12))   # tpr không giảm -> chỉ số đầu tiên đạt
    return float(fpr[idx]), float(tpr[idx]), float(thr[idx])


def fpr_at_tpr(y_true, y_score, target_tpr: float = 0.95) -> float:
    return operating_point_at_tpr(y_true, y_score, target_tpr)[0]


def _pct_key(p: float) -> str:
    """0.1 -> '10pct', 0.01 -> '1pct', 0.001 -> '0p1pct' (an toàn cho tên khoá/macro)."""
    s = f"{p * 100:g}".replace(".", "p")
    return f"{s}pct"


def base_rate_precision(y_true, y_score, prevalences=(0.10, 0.01, 0.001), target_tpr: float = 0.95) -> dict:
    """Precision triển khai ước lượng ở base-rate thực (RQF-07).

    Lấy (fpr, tpr) tại TPR≈target trên ROC rồi hiệu chỉnh theo tỉ lệ webshell p:
        precision(p) = tpr·p / (tpr·p + fpr·(1−p))
    (độc lập với tỉ lệ lớp của tập test). Trả {p: precision}. fpr=0 -> 1.0; 1 lớp -> nan.
    """
    fpr, tpr, _ = operating_point_at_tpr(y_true, y_score, target_tpr)
    out = {}
    for p in prevalences:
        if math.isnan(fpr):
            out[p] = math.nan
            continue
        num = tpr * p
        den = num + fpr * (1.0 - p)
        out[p] = float(num / den) if den > 0 else math.nan
    return out


def evaluate(y_true, y_score, threshold: float = 0.5,
             prevalences=(0.10, 0.01, 0.001), target_tpr: float = 0.95) -> dict:
    """Trả dict phẳng (mọi giá trị là float để gộp seed):
    f1_macro, accuracy, precision, recall, mcc, pr_auc, roc_auc, fpr_at_tpr95,
    prec_at_base_{10pct,1pct,0p1pct}, threshold, n, n_pos.
    Metric ngưỡng-độc-lập (PR-AUC, ROC-AUC, FPR@TPR95, base-rate) = nan khi test chỉ có 1 lớp.
    """
    y_true = np.asarray(y_true).astype(int).ravel()
    y_score = np.asarray(y_score, dtype=float).ravel()
    if y_true.shape != y_score.shape:
        raise ValueError(f"y_true {y_true.shape} != y_score {y_score.shape}")
    if y_true.size == 0:
        raise ValueError("evaluate() nhận mảng rỗng")
    y_pred = (y_score >= threshold).astype(int)
    two = _two_classes(y_true)
    res = {
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", labels=[0, 1], zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "mcc": float(matthews_corrcoef(y_true, y_pred)),
        "pr_auc": float(average_precision_score(y_true, y_score)) if two else math.nan,
        "roc_auc": float(roc_auc_score(y_true, y_score)) if two else math.nan,
        "fpr_at_tpr95": fpr_at_tpr(y_true, y_score, target_tpr),
    }
    for p, v in base_rate_precision(y_true, y_score, prevalences, target_tpr).items():
        res[f"prec_at_base_{_pct_key(p)}"] = v
    res["threshold"] = float(threshold)
    res["n"] = float(y_true.size)
    res["n_pos"] = float(y_true.sum())
    return res


# ---------------------------------------------------------------- numbers.tex
_DIGIT_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
# metric KHÔNG nhân 100 khi in (không phải tỉ lệ ∈[0,1])
_NON_PERCENT = {"n", "n_pos", "threshold", "mcc"}


def tex_macro_name(*parts: str) -> str:
    r"""Tên macro LaTeX chỉ gồm chữ cái: ('HiPaG','f1_macro') -> 'HiPaGFOneMacro'."""
    out = []
    for part in parts:
        for tok in re.findall(r"[A-Za-z]+|\d", str(part)):
            tok = _DIGIT_WORDS[int(tok)] if tok.isdigit() else tok
            out.append(tok[0].upper() + tok[1:])
    name = "".join(out)
    if not name.isalpha():
        raise ValueError(f"Tên macro không hợp lệ: {name!r}")
    return name


def _fmt_value(metric: str, mean: float, sd: float, digits: int = 2) -> str:
    if mean is None or math.isnan(mean):
        return r"n/a"
    scale = 1.0 if metric in _NON_PERCENT else 100.0
    d = 0 if metric in {"n", "n_pos"} else (3 if metric == "mcc" else digits)
    m = f"{mean * scale:.{d}f}"
    if sd is None or math.isnan(sd):
        return m
    return rf"\ensuremath{{{m} \pm {sd * scale:.{d}f}}}"


_MACRO_RE = re.compile(r"^\\(?:newcommand|renewcommand|providecommand)\{\\([A-Za-z]+)\}")


def write_numbers_tex(agg: dict, path: str, prefix: str = "HiPaG", metrics=None, n_seeds: int | None = None,
                      metric_name_aliases: dict[str, str] | None = None):
    r"""Ghi macro \newcommand để paper \input (tránh gõ tay số -> chống mâu thuẫn P1 vs P2).

    agg    : {metric: (mean, sd)} (từ utils.metrics.aggregate_seeds), tỉ lệ ∈[0,1] in ra dạng %.
    prefix : tiền tố macro, vd 'HiPaG' hoặc 'RqFourNoESem' -> \HiPaGFOneMacro.
    Gộp vào file có sẵn: macro trùng tên bị thay, macro khác (RQ khác) giữ nguyên.
    Trả danh sách tên macro đã ghi.
    """
    path = Path(path)
    lines = path.read_text().splitlines() if path.exists() else [
        "% Result macros -- written by eval.py (write_numbers_tex); main.tex does \\input{numbers.tex}.",
        "% Do not edit by hand: re-run scripts/run_experiment.py to update.",
    ]
    keys = list(agg) if metrics is None else [m for m in metrics if m in agg]
    new: dict[str, str] = {}
    for k in keys:
        mean, sd = agg[k]
        aliases = metric_name_aliases or {}
        name = prefix + aliases[k] if k in aliases else tex_macro_name(prefix, k)
        note = f"  % {prefix}:{k}" + (f" (n_seeds={n_seeds})" if n_seeds else "")
        new[name] = f"\\newcommand{{\\{name}}}{{{_fmt_value(k, mean, sd)}}}{note}"
    kept, done = [], set()
    for ln in lines:
        m = _MACRO_RE.match(ln.strip())
        if m and m.group(1) in new:
            if m.group(1) not in done:
                kept.append(new[m.group(1)]); done.add(m.group(1))
            continue
        kept.append(ln)
    kept.extend(v for n, v in new.items() if n not in done)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept) + "\n")
    return list(new)
