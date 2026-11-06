"""Dataset PyG đọc đồ thị đã dựng (data/features_small/*.pt, mỗi file một HeteroData).

split_csv (do scripts/dataset/05_make_splits.py ghi) cần các cột:
    sample_id, path, label, split [, source, cluster_id, level]
`path` tương đối theo features_dir. Đồ thị > max_bytes (mặc định 10MB) bị bỏ và ghi vào `self.skipped`.
"""
from __future__ import annotations

import csv
from pathlib import Path

import torch
from torch.utils.data import Dataset

REQUIRED_COLS = {"sample_id", "path", "label", "split"}


class WebshellGraphDataset(Dataset):
    def __init__(self, split_csv: str, features_dir: str, split: str | None = None,
                 max_bytes: int = 10 * 1024 * 1024, where: dict | None = None):
        """split : chỉ lấy hàng có cột split == giá trị này (None = mọi hàng).
        where : lọc thêm theo cột, vd {'level': 'L3'} cho ma trận obfuscation (RQ2)."""
        self.split_csv = split_csv
        self.features_dir = Path(features_dir)
        self.rows: list[dict] = []
        self.skipped: list[tuple[str, str]] = []
        with open(split_csv, newline="") as f:
            reader = csv.DictReader(f)
            missing = REQUIRED_COLS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{split_csv} thiếu cột {sorted(missing)}")
            for r in reader:
                if split is not None and r["split"] != split:
                    continue
                if where and any(str(r.get(k)) != str(v) for k, v in where.items()):
                    continue
                p = self.features_dir / r["path"]
                if not p.exists():
                    self.skipped.append((r["sample_id"], "missing"))
                elif p.stat().st_size > max_bytes:
                    self.skipped.append((r["sample_id"], "too_large"))
                else:
                    self.rows.append(r)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        d = torch.load(self.features_dir / r["path"], weights_only=False)
        d.y = torch.tensor([float(r["label"])])          # nhãn trong CSV là nguồn chân lý
        return d

    @property
    def labels(self) -> list[int]:
        return [int(float(r["label"])) for r in self.rows]
