"""Metrics chuẩn nhóm: F1_macro, acc, precision, recall, MCC, PR-AUC, FPR@TPR95,
+ base-rate precision @ {10%,1%,0.1%} (RQF-07). Xuất macro vào paper/numbers.tex. VỎ."""
from __future__ import annotations


def base_rate_precision(y_true, y_score, prevalences=(0.10, 0.01, 0.001), target_tpr: float = 0.95):
    """Precision triển khai ước lượng ở base-rate thực (RQF-07).
    Gợi ý: lấy (fpr, tpr) tại TPR~target trên ROC; precision = tpr*p / (tpr*p + fpr*(1-p))."""
    raise NotImplementedError  # TODO


def evaluate(y_true, y_score, threshold: float = 0.5) -> dict:
    """Trả dict: f1_macro, mcc, pr_auc, fpr_at_tpr95, base_rate_precision."""
    raise NotImplementedError  # TODO


def write_numbers_tex(agg: dict, path: str):
    r"""Ghi macro \newcommand để paper \input (tránh gõ tay số -> chống mâu thuẫn P1 vs P2)."""
    raise NotImplementedError  # TODO
