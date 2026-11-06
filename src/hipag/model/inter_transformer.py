"""Tier 3 — Inter-procedural Graph Transformer (TransformerConv/UniMP) trên call+include graph.

Nút = function (đã pool từ statement). edge_attr = one-hot [call, include].
Function cô lập (không có cạnh) vẫn được cập nhật qua root_weight (skip connection).
"""
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import TransformerConv


class InterProceduralTransformer(nn.Module):
    def __init__(self, d_in: int, hidden: int = 128, heads: int = 2, layers: int = 2,
                 edge_dim: int | None = 2, dropout: float = 0.1):
        super().__init__()
        if hidden % heads:
            raise ValueError(f"hidden={hidden} phải chia hết cho heads={heads}")
        self.inp = nn.Linear(d_in, hidden) if d_in != hidden else nn.Identity()
        self.convs = nn.ModuleList(
            TransformerConv(hidden, hidden // heads, heads=heads, edge_dim=edge_dim,
                            dropout=dropout, root_weight=True)
            for _ in range(layers))
        self.norms = nn.ModuleList(nn.LayerNorm(hidden) for _ in range(layers))
        self.dropout = dropout

    def forward(self, x, edge_index, edge_attr=None):
        h = self.inp(x)
        for conv, norm in zip(self.convs, self.norms):
            m = conv(h, edge_index, edge_attr=edge_attr)
            h = norm(h + F.dropout(F.elu(m), self.dropout, self.training))
        return h
