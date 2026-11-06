"""Batch HeteroData: dùng PyG DataLoader (tự dịch chỉ số cạnh + tạo vector batch cho stmt/func)."""
from __future__ import annotations

import torch
from torch_geometric.loader import DataLoader


def make_loader(dataset, batch_size: int = 32, shuffle: bool = False, num_workers: int = 0,
                seed: int | None = None) -> DataLoader:
    """Loader tái lập được: thứ tự shuffle cố định theo `seed`."""
    g = None
    if seed is not None:
        g = torch.Generator()
        g.manual_seed(seed)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, num_workers=num_workers,
                      generator=g, persistent_workers=num_workers > 0)
