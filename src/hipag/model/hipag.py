"""HiPaG — mô hình đầy đủ: 3 tầng + taint predictor + đặc trưng toàn cục + head. VỎ.

Lắp: Token-Transformer (tier1) -> IntraGATv2 (tier2, + E_sem từ TaintDependencyPredictor)
     -> InterProceduralTransformer (tier3) -> pool -> concat global features -> head.
"""
import torch.nn as nn


class HiPaG(nn.Module):
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        # TODO: khởi tạo 4 khối con theo cfg["model"]; chọn pool theo cfg["model"]["pool"]

    def forward(self, batch):
        raise NotImplementedError  # TODO
