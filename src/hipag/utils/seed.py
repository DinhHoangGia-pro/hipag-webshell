"""Cố định seed cho reproducibility (RQF-09)."""
from __future__ import annotations

import os
import random

import numpy as np


def set_seed(seed: int, deterministic: bool = True) -> None:
    """Cố định random/numpy/torch (+CUDA). `deterministic` bật cudnn.deterministic.

    Lưu ý: một số kernel scatter của PyG trên CUDA vẫn không tất định tuyệt đối;
    vì vậy kết quả luôn báo mean±sd qua ≥5 seed thay vì dựa vào một lần chạy.
    """
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch
    except ImportError:  # cho phép dùng utils mà không có torch
        return
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if deterministic:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
