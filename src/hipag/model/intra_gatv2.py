"""Tier 2 — GATv2 trong hàm trên E_seq/E_skip/E_cfg/E_dfg/E_sem. Kế thừa LOGWAT/T-CFBG.

edge_attr = [one-hot loại cạnh | trọng số]; trọng số = P(E_sem) với cạnh học được, 1 với cạnh cấu trúc.
Như vậy gradient của loss phát hiện chảy ngược vào Taint-Dependency Predictor qua edge_attr.
"""
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATv2Conv


class IntraFunctionGATv2(nn.Module):
    def __init__(self, d_in: int, hidden: int = 128, heads: int = 2, layers: int = 2,
                 edge_dim: int | None = None, dropout: float = 0.1):
        super().__init__()
        if hidden % heads:
            raise ValueError(f"hidden={hidden} phải chia hết cho heads={heads}")
        self.inp = nn.Linear(d_in, hidden) if d_in != hidden else nn.Identity()
        self.convs = nn.ModuleList(
            GATv2Conv(hidden, hidden // heads, heads=heads, edge_dim=edge_dim,
                      add_self_loops=True, fill_value="mean", dropout=dropout)
            for _ in range(layers))
        self.norms = nn.ModuleList(nn.LayerNorm(hidden) for _ in range(layers))
        self.dropout = dropout

    def forward(self, x, edge_index, edge_attr=None):
        h = self.inp(x)
        for conv, norm in zip(self.convs, self.norms):
            m = conv(h, edge_index, edge_attr=edge_attr)
            h = norm(h + F.dropout(F.elu(m), self.dropout, self.training))
        return h
