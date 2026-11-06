"""Tier 1 — Token-Sequence Transformer (embedding theo ngữ cảnh trong statement). Kế thừa T-CFBG.

Vào: x_tok [S, L] id token (0 = PAD). Ra: [S, d_embed] (masked mean-pool sau encoder).
`use_encoder=False` -> embedding TĨNH (mean các token, không ngữ cảnh) — ablation no_token_transformer.
"""
import torch
import torch.nn as nn


class TokenSequenceTransformer(nn.Module):
    def __init__(self, vocab_size: int = 4096, d_embed: int = 64, heads: int = 4, layers: int = 2,
                 max_len: int = 32, dropout: float = 0.1, use_encoder: bool = True):
        super().__init__()
        self.d_embed = d_embed
        self.use_encoder = use_encoder
        self.tok = nn.Embedding(vocab_size, d_embed, padding_idx=0)
        self.pos = nn.Embedding(max_len, d_embed) if use_encoder else None
        self.encoder = None
        if use_encoder:
            layer = nn.TransformerEncoderLayer(d_embed, heads, dim_feedforward=2 * d_embed,
                                               dropout=dropout, batch_first=True, norm_first=True)
            self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)

    def forward(self, x, key_padding_mask=None):
        """x: [S, L] long. key_padding_mask: [S, L] bool, True = PAD (mặc định suy từ x == 0)."""
        if x.numel() == 0:
            return x.new_zeros((x.shape[0], self.d_embed), dtype=torch.float)
        pad = (x == 0) if key_padding_mask is None else key_padding_mask
        valid = ~pad
        e = self.tok(x)
        if self.use_encoder:
            pos = torch.arange(x.shape[1], device=x.device)
            e = e + self.pos(pos)[None]
            # Hàng toàn PAD (statement rỗng) làm softmax ra NaN -> mở vị trí 0 cho hàng đó.
            attn_pad = pad.clone()
            attn_pad[pad.all(dim=1), 0] = False
            e = self.encoder(e, src_key_padding_mask=attn_pad)
        w = valid.unsqueeze(-1).float()
        return (e * w).sum(1) / w.sum(1).clamp(min=1.0)
