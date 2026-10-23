"""Tier 1 — Token-Sequence Transformer (embedding theo ngữ cảnh trong block). Kế thừa T-CFBG.

VỎ: điền encoder + positional embedding.
"""
import torch.nn as nn


class TokenSequenceTransformer(nn.Module):
    def __init__(self, d_embed: int = 64, heads: int = 4, layers: int = 2):
        super().__init__()
        self.d_embed = d_embed
        # TODO: nn.TransformerEncoder + positional embedding

    def forward(self, x, key_padding_mask=None):
        raise NotImplementedError  # TODO
