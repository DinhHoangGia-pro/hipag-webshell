"""Learned Taint-Dependency Predictor (RQF-06).

Thay bảng luật source->sink cứng (kiểu risk-weight gán tay của GlareShell / 9-cặp của LOGWAT)
bằng link-prediction YẾU-GIÁM-SÁT trên biểu diễn nút:

    P(e_sem_{i->j} = 1) = sigmoid( MLP([ h_i || h_j ]) )

Giám sát yếu:
  - positive : cặp (node source, node sink) có đường đi trong cửa sổ CFG/DFG (reachable) — "nên có cạnh E_sem".
  - negative : cặp lấy mẫu không thoả điều kiện seed, tỉ lệ `neg_per_pos`.
Loss = BCE. Ngưỡng `tau` hiệu chỉnh trên validation để tối đa F1 của cạnh, có SÀN `tau_floor`.

Chọn cạnh E_sem (select_edges): giữ cặp có p > max(tau, tau_floor) VÀ nằm trong TOP-K theo p
trong số các ứng viên cùng đích (mỗi sink nhận ≤ top_k cạnh vào) — chặn bùng số cạnh khi
predictor chưa phân biệt được (τ hiệu chỉnh tụt thấp -> giữ gần hết ứng viên).

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
    def __init__(self, d_in: int, mlp_hidden: int = 128, tau: float = 0.5, dropout: float = 0.1,
                 tau_floor: float = 0.0, top_k: int | None = None):
        super().__init__()
        self.tau = tau
        self.tau_floor = tau_floor
        self.top_k = top_k
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

    @property
    def effective_tau(self) -> float:
        return max(float(self.tau), float(self.tau_floor))

    def select_edges(self, pairs: torch.Tensor, p: torch.Tensor, tau: float | None = None,
                     top_k: int | None = -1) -> torch.Tensor:
        """Mặt nạ bool [E]: p > max(tau, tau_floor) VÀ top-k theo p trong mỗi đích (sink).
        top_k=-1 -> dùng self.top_k; None/≤0 -> không giới hạn. Mặt nạ không mang gradient."""
        tau = self.effective_tau if tau is None else max(float(tau), float(self.tau_floor))
        k = self.top_k if top_k == -1 else top_k
        p = p.detach()
        return (p > tau) & topk_per_dst(pairs[1], p, k)

    @torch.no_grad()
    def predict_edges(self, h: torch.Tensor, candidate_pairs: torch.Tensor, tau: float | None = None,
                      top_k: int | None = -1):
        """Trả (kept_pairs [2, K], probs [K]) — các cạnh E_sem được sinh (ngưỡng có sàn + top-k/sink)."""
        if candidate_pairs.numel() == 0:
            return candidate_pairs, torch.empty(0, device=h.device)
        p = torch.sigmoid(self.edge_logit(h, candidate_pairs))
        keep = self.select_edges(candidate_pairs, p, tau, top_k)
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


def build_seed_pairs(node_roles, reachable, neg_per_pos: int = 5, max_pos: int = 4096, seed: int | None = None,
                     candidates=None, hard_frac: float = 0.5, extra_pos=None, exclude_neg=None):
    """Sinh cặp giám sát yếu từ seed + khả năng tới được (reachable).

    node_roles : seq độ dài N, phần tử ∈ {'source','sink','decode',None} (graph.taint_seeds.primary_role).
    reachable  : callable(i, j) -> bool — True nếu j tới được từ i trong cửa sổ CFG/DFG.
    candidates : (tuỳ chọn) list cặp (i, j) ứng viên E_sem. Nếu có, ~`hard_frac` mẫu âm được lấy
                 từ các ứng viên KHÔNG phải positive (hard negative — cùng phân phối với lúc suy
                 luận, vì predictor chỉ chấm điểm trên ứng viên); phần còn lại lấy ngẫu nhiên.
    extra_pos  : positive bổ sung (vd source->sink chặt bridge liên thủ tục) — gộp, khử trùng.
    exclude_neg: cặp KHÔNG được làm mẫu âm (vd mọi ứng viên có kiểu source->sink chỉ-ứng-viên: chưa chắc là
                 taint nên không gán nhãn âm — NHÃN CHẶT cả hai phía).
    Trả (pos_pairs [2, P], neg_pairs [2, Nneg]) LongTensor.
    """
    rng = random.Random(seed)
    N = len(node_roles)
    sources = [i for i, r in enumerate(node_roles) if r == "source"]
    sinks = [i for i, r in enumerate(node_roles) if r == "sink"]

    pos = [(i, j) for i in sources for j in sinks if i != j and reachable(i, j)]
    if extra_pos:
        seen = set(pos)
        pos += [p for p in map(tuple, extra_pos) if p not in seen and not seen.add(p)]
    if len(pos) > max_pos:
        pos = rng.sample(pos, max_pos)

    n_neg = len(pos) * neg_per_pos
    neg: set[tuple[int, int]] = set()
    pos_set = set(pos)
    excl = set(map(tuple, exclude_neg)) if exclude_neg else set()
    if candidates and n_neg:
        pool = [c for c in candidates if c not in pos_set and c not in excl
                and not (node_roles[c[0]] == "source" and node_roles[c[1]] == "sink")]
        k = min(len(pool), int(round(n_neg * hard_frac)))
        neg.update(rng.sample(pool, k))
    guard = 0
    while len(neg) < n_neg and guard < max(n_neg * 20, 1) and N > 1:
        guard += 1
        i, j = rng.randrange(N), rng.randrange(N)
        if i == j:
            continue
        if node_roles[i] == "source" and node_roles[j] == "sink" and reachable(i, j):
            continue  # đó là positive, bỏ
        if (i, j) in pos_set or (i, j) in excl:
            continue
        neg.add((i, j))

    def to_t(pairs):
        return (torch.tensor(pairs, dtype=torch.long).t().contiguous()
                if pairs else torch.empty(2, 0, dtype=torch.long))

    return to_t(pos), to_t(list(neg))


@torch.no_grad()
def topk_per_dst(dst: torch.Tensor, score: torch.Tensor, k: int | None) -> torch.Tensor:
    """Mặt nạ bool [E]: True nếu cạnh nằm trong k cạnh có score cao nhất cùng đích `dst`.
    Hoà điểm: ưu tiên chỉ số cạnh nhỏ hơn (tất định). k None/≤0 -> giữ hết."""
    E = dst.numel()
    if k is None or k <= 0 or E == 0:
        return torch.ones(E, dtype=torch.bool, device=dst.device)
    order = torch.argsort(score, descending=True, stable=True)          # theo điểm giảm dần
    perm = order[torch.argsort(dst[order], stable=True)]                # gom theo đích, giữ thứ tự điểm
    ds = dst[perm]
    idx = torch.arange(E, device=dst.device)
    is_start = torch.ones(E, dtype=torch.bool, device=dst.device)
    is_start[1:] = ds[1:] != ds[:-1]
    group_start = torch.cummax(torch.where(is_start, idx, torch.zeros_like(idx)), dim=0).values
    mask = torch.zeros(E, dtype=torch.bool, device=dst.device)
    mask[perm] = (idx - group_start) < k
    return mask


@torch.no_grad()
def calibrate_tau(probs: torch.Tensor, labels: torch.Tensor, steps: int = 101, tau_floor: float = 0.0) -> float:
    """Chọn tau ≥ tau_floor tối đa F1 cạnh trên validation. probs, labels: [M] (labels ∈ {0,1})."""
    best_tau, best_f1 = max(0.5, tau_floor), -1.0
    for k in range(steps):
        t = k / (steps - 1)
        if t < tau_floor:
            continue
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
