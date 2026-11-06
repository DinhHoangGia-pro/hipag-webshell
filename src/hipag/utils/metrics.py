"""Gộp N-seed -> mean ± sd (RQF-07/09)."""
from __future__ import annotations

import math
from numbers import Number

import numpy as np


def aggregate_seeds(per_seed: list[dict]) -> dict:
    """Trả {metric: (mean, sd)} từ danh sách dict kết quả mỗi seed.

    - Chỉ gộp giá trị số vô hướng (bỏ qua list/dict/str — vd mảng y_score).
    - sd là độ lệch chuẩn MẪU (ddof=1); với 1 seed thì sd = nan (không bịa độ chắc chắn).
    - Giá trị nan (vd PR-AUC khi test chỉ có một lớp) bị loại khỏi mean/sd; nếu mọi seed
      đều nan thì trả (nan, nan).
    - Metric thiếu ở một số seed vẫn được gộp trên các seed có nó.
    """
    if not per_seed:
        return {}
    keys: list[str] = []
    for d in per_seed:
        for k, v in d.items():
            if k not in keys and isinstance(v, Number) and not isinstance(v, bool):
                keys.append(k)
    out: dict[str, tuple[float, float]] = {}
    for k in keys:
        vals = np.array([float(d[k]) for d in per_seed
                         if isinstance(d.get(k), Number) and not isinstance(d.get(k), bool)],
                        dtype=float)
        vals = vals[~np.isnan(vals)]
        if vals.size == 0:
            out[k] = (math.nan, math.nan)
        elif vals.size == 1:
            out[k] = (float(vals[0]), math.nan)
        else:
            out[k] = (float(vals.mean()), float(vals.std(ddof=1)))
    return out


def format_mean_sd(mean: float, sd: float, scale: float = 100.0, digits: int = 2) -> str:
    """'93.12 ± 0.45' (mặc định nhân 100 -> %). nan -> 'n/a'."""
    if mean is None or (isinstance(mean, float) and math.isnan(mean)):
        return "n/a"
    m = f"{mean * scale:.{digits}f}"
    if sd is None or (isinstance(sd, float) and math.isnan(sd)):
        return m
    return f"{m} ± {sd * scale:.{digits}f}"
