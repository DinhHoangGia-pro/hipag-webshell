"""Huấn luyện một seed (resume, per-epoch progress, num_workers — giống H-GNN). VỎ."""
from __future__ import annotations
import argparse


def train_one_seed(cfg: dict, seed: int):
    raise NotImplementedError  # TODO


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    # TODO: load yaml -> cfg; train_one_seed(cfg, args.seed)
