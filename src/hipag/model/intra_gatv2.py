"""Tier 2 — GATv2 trong hàm trên CFG+DFG+E_sem. Kế thừa LOGWAT/T-CFBG. VỎ."""
import torch.nn as nn


class IntraFunctionGATv2(nn.Module):
    def __init__(self, d_in: int, hidden: int = 128, heads: int = 2, layers: int = 2):
        super().__init__()
        # TODO: stack GATv2Conv (torch_geometric.nn.GATv2Conv)

    def forward(self, x, edge_index):
        raise NotImplementedError  # TODO
