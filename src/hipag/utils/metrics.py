"""Gộp N-seed -> mean ± sd. VỎ."""
from __future__ import annotations


def aggregate_seeds(per_seed: list[dict]) -> dict:
    """Trả {metric: (mean, sd)} từ danh sách dict kết quả mỗi seed."""
    raise NotImplementedError  # TODO
