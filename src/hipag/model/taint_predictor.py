"""Learned Taint-Dependency Predictor (RQF-06).

Thay bảng luật source->sink cứng (kiểu risk-weight gán tay của GlareShell / 9-cặp của LOGWAT)
bằng link-prediction YẾU-GIÁM-SÁT trên biểu diễn nút:

    P(e_sem_{i->j} = 1) = sigmoid( MLP([ h_i || h_j ]) )

Giám sát yếu:
  - positive : cặp (node source, node sink) có đường đi trong cửa sổ CFG/DFG (reachable) — "nên có cạnh E_sem".
  - negative : cặp lấy mẫu không thoả điều kiện seed, tỉ lệ `neg_per_pos`.
Loss = BCE. Ngưỡng `tau` hiệu chỉnh trên validation để tối đa F1 của cạnh.

I/O:
  h               : Tensor [N, d]     — biểu diễn ẩn các nút (sau tier-1/tier-2).
  candidate_pairs : LongTensor [2, E] — (src, dst) có HƯỚNG; thứ tự src->dst có nghĩa.
"""
from __future__ import annotations
import random

import torch
import torch.nn as nn
import torch.nn.functional as F


class TaintDependencyPredictor(nn.Module):
    def __init__(self, d_in: int, mlp_hidden: int = 128, tau: float = 0.5, dropout: float = 0.1):
        super().__init__()
        self.tau = tau
        self.mlp = nn.Sequential(
            nn.Linear(2 * d_in, mlp_hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(mlp_hidden, 1),
        )

    def edge_logit(self, h: torch.Tensor, pairs: torch.Tensor) -> torch.Tensor:
        """pairs [2, E] = (src, dst). Trả logit [E] cho cạnh có hướng src->dst."""
        src, dst = pairs[0], pairs[1]
        feat = torch.cat([h[src], h[dst]], dim=-1)   # directed: src||dst, không đối xứng
        return self.mlp(feat).squeeze(-1)

    def forward(self, h: torch.Tensor, candidate_pairs: torch.Tensor) -> torch.Tensor:
        return self.edge_logit(h, candidate_pairs)

    @torch.no_grad()
    def predict_edges(self, h: torch.Tensor, candidate_pairs: torch.Tensor, tau: float | None = None):
        """Trả (kept_pairs [2, K], probs [K]) với prob > tau — tức các cạnh E_sem được sinh."""
        tau = self.tau if tau is None else tau
        if candidate_pairs.numel() == 0:
            return candidate_pairs, torch.empty(0, device=h.device)
        p = torch.sigmoid(self.edge_logit(h, candidate_pairs))
        keep = p > tau
        return candidate_pairs[:, keep], p[keep]

    def bce_loss(self, h: torch.Tensor, pos_pairs: torch.Tensor, neg_pairs: torch.Tensor,
                 pos_weight: float | None = None) -> torch.Tensor:
        """BCE yếu-giám-sát trên pos/neg pairs. Bỏ qua gọn khi thiếu một phía."""
        logits, labels = [], []
        if pos_pairs.numel():
            lp = self.edge_logit(h, pos_pairs)
            logits.append(lp); labels.append(torch.ones_like(lp))
        if neg_pairs.numel():
            ln = self.edge_logit(h, neg_pairs)
            logits.append(ln); labels.append(torch.zeros_like(ln))
        if not logits:
            return h.sum() * 0.0   # không có giám sát ở batch này
        logits = torch.cat(logits); labels = torch.cat(labels)
        pw = None if pos_weight is None else torch.tensor(pos_weight, device=logits.device)
        return F.binary_cross_entropy_with_logits(logits, labels, pos_weight=pw)


def build_seed_pairs(node_roles, reachable, neg_per_pos: int = 5, max_pos: int = 4096, seed: int | None = None):
    """Sinh cặp giám sát yếu từ seed + khả năng tới được (reachable).

    node_roles : seq độ dài N, phần tử ∈ {'source','sink','decode',None} (taint_seeds.classify_token).
    reachable  : callable(i, j) -> bool — True nếu j tới được từ i trong cửa sổ CFG/DFG.
    Trả (pos_pairs [2, P], neg_pairs [2, Nneg]) LongTensor.
    """
    rng = random.Random(seed)
    N = len(node_roles)
    sources = [i for i, r in enumerate(node_roles) if r == "source"]
    sinks = [i for i, r in enumerate(node_roles) if r == "sink"]

    pos = [(i, j) for i in sources for j in sinks if i != j and reachable(i, j)]
    if len(pos) > max_pos:
        pos = rng.sample(pos, max_pos)

    n_neg = len(pos) * neg_per_pos
    neg: set[tuple[int, int]] = set()
    guard = 0
    while len(neg) < n_neg and guard < max(n_neg * 20, 1) and N > 1:
        guard += 1
        i, j = rng.randrange(N), rng.randrange(N)
        if i == j:
            continue
        if node_roles[i] == "source" and node_roles[j] == "sink" and reachable(i, j):
            continue  # đó là positive, bỏ
        neg.add((i, j))

    def to_t(pairs):
        return (torch.tensor(pairs, dtype=torch.long).t().contiguous()
                if pairs else torch.empty(2, 0, dtype=torch.long))

    return to_t(pos), to_t(list(neg))


@torch.no_grad()
def calibrate_tau(probs: torch.Tensor, labels: torch.Tensor, steps: int = 101) -> float:
    """Chọn tau tối đa F1 cạnh trên validation. probs, labels: [M] (labels ∈ {0,1})."""
    best_tau, best_f1 = 0.5, -1.0
    for k in range(steps):
        t = k / (steps - 1)
        pred = probs > t
        tp = (pred & (labels > 0.5)).sum().item()
        fp = (pred & (labels <= 0.5)).sum().item()
        fn = ((~pred) & (labels > 0.5)).sum().item()
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        if f1 > best_f1:
            best_f1, best_tau = f1, t
    return best_tau
