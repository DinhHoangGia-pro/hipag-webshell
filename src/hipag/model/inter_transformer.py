"""Tier 3 — Inter-procedural Graph Transformer (TransformerConv/UniMP) trên call+include graph. VỎ."""
import torch.nn as nn


class InterProceduralTransformer(nn.Module):
    def __init__(self, d_in: int, hidden: int = 128, heads: int = 2, layers: int = 2):
        super().__init__()
        # TODO: stack TransformerConv

    def forward(self, x, edge_index):
        raise NotImplementedError  # TODO
