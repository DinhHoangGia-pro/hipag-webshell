"""Dataset PyG đọc đồ thị đã dựng (data/features_small). VỎ: cap statements/functions, drop graph >10MB."""
from __future__ import annotations
from torch.utils.data import Dataset


class WebshellGraphDataset(Dataset):
    def __init__(self, split_csv: str, features_dir: str):
        self.split_csv = split_csv
        self.features_dir = features_dir
        # TODO: load rows

    def __len__(self):
        raise NotImplementedError  # TODO

    def __getitem__(self, i):
        raise NotImplementedError  # TODO
