"""Nạp YAML có khoá `inherit` (config thí nghiệm kế thừa config model)."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml


def deep_merge(base: dict, override: dict) -> dict:
    """Trộn đệ quy: giá trị ở `override` thắng; dict lồng được trộn tiếp."""
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path: str | Path, root: str | Path | None = None, _seen: set | None = None) -> dict:
    """Đọc YAML; nếu có `inherit: <path>` thì nạp file cha (đường dẫn tương đối theo `root`,
    mặc định thư mục làm việc; nếu không thấy thì thử tương đối theo file con) rồi trộn."""
    path = Path(path)
    _seen = set() if _seen is None else _seen
    key = str(path.resolve())
    if key in _seen:
        raise ValueError(f"Vòng lặp inherit tại {path}")
    _seen.add(key)
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}
    parent = cfg.pop("inherit", None)
    if parent is None:
        return cfg
    cand = Path(root or ".") / parent
    if not cand.exists():
        cand = path.parent / parent
    return deep_merge(load_config(cand, root, _seen), cfg)
