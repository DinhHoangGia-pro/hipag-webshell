"""HiPaG — mô hình đầy đủ: 3 tầng + taint predictor + đặc trưng toàn cục + head.

Luồng:
  x_tok --Tier1 TokenSequenceTransformer--> e_tok ; [e_tok || x_stmt] --proj--> h0
  h0 --TaintDependencyPredictor trên cặp CAND--> E_sem (p > max(tau,tau_floor), top-k/sink, edge weight = p)
     (warmup_epochs epoch đầu: E_sem = cạnh LUẬT = SEM_POS, tức seed source->sink tới được; predictor
      vẫn học qua taint_loss rồi mới thay thế — train.py gọi model.set_epoch(epoch))
  h0 --Tier2 IntraFunctionGATv2 (seq/skip/cfg/dfg/sem)--> h_stmt --pool theo function--> h_func
  h_func --Tier3 InterProceduralTransformer (call/include)--> --pool theo file--> g
  [g || global_x] --head--> logit (webshell)

Biến thể ablation: cfg["model"]["ablation"] ∈ ABLATIONS.
"""
from __future__ import annotations

import torch
import torch.nn as nn
from torch_geometric.utils import scatter

from ..graph.edges import CAND, FUNC, IN_FUNC, INTER_TYPES, INTRA_TYPES, PYG_EDGE, SEM_NEG, SEM_POS, STMT
from ..graph.node_features import GLOBAL_FEAT_DIM, NODE_FEAT_DIM
from .inter_transformer import InterProceduralTransformer
from .intra_gatv2 import IntraFunctionGATv2
from .taint_predictor import TaintDependencyPredictor, topk_per_dst
from .token_transformer import TokenSequenceTransformer

ABLATIONS = [
    "full",
    "no_token_transformer",   # tier1 -> embedding tĩnh
    "no_e_sem",               # bỏ cạnh ngữ nghĩa (và loss taint)
    "no_e_dfg",               # bỏ data-flow
    "no_inter_transformer",   # bỏ tầng file
    "no_global_features",
    "pool_mean",              # max -> mean
    "rule_e_sem",             # E_sem = luật cứng source->sink tới được (−taint-predictor, RQF-10)
]
_E_DIM = len(INTRA_TYPES) + 1   # one-hot loại cạnh + trọng số


class HiPaG(nn.Module):
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        m = cfg["model"]
        self.ablation = m.get("ablation", "full")
        if self.ablation not in ABLATIONS:
            raise ValueError(f"ablation không hợp lệ: {self.ablation!r}; chọn trong {ABLATIONS}")
        tt, intra, inter, tp = m["token_transformer"], m["intra_gatv2"], m["inter_transformer"], m["taint_predictor"]
        drop = m.get("dropout", 0.1)
        hidden = intra["hidden"]

        self.tier1 = TokenSequenceTransformer(
            vocab_size=tt.get("vocab_size", 4096), d_embed=tt["d_embed"], heads=tt["heads"],
            layers=tt["layers"], max_len=tt.get("max_len", 32), dropout=drop,
            use_encoder=self.ablation != "no_token_transformer")
        self.stmt_proj = nn.Sequential(nn.Linear(tt["d_embed"] + NODE_FEAT_DIM, hidden), nn.ReLU())

        self.learned_sem = self.ablation not in ("no_e_sem", "rule_e_sem")
        self.top_k = tp.get("top_k", 8)
        # pos_weight của BCE cạnh taint: 'auto' = n_neg/n_pos mỗi batch (cân bằng lại tỉ lệ 1:neg_per_pos,
        # để xác suất KHÔNG co về tiên nghiệm ~1/(1+neg_per_pos) — nếu không, tau_floor tuyệt đối cắt hết cạnh)
        self.taint_pos_weight = tp.get("pos_weight", "auto")
        self.warmup_epochs = int(tp.get("warmup_epochs", 0)) if self.learned_sem else 0
        self.taint = (TaintDependencyPredictor(hidden, tp["mlp_hidden"], tp.get("tau", 0.5), drop,
                                               tau_floor=tp.get("tau_floor", 0.0), top_k=self.top_k)
                      if self.learned_sem else None)
        # 'rule' | 'learned' | 'none'. Mặc định 'learned' (suy luận); train.py chuyển theo epoch.
        self.sem_mode = {"no_e_sem": "none", "rule_e_sem": "rule"}.get(self.ablation, "learned")
        self.tier2 = IntraFunctionGATv2(hidden, hidden, intra["heads"], intra["layers"], _E_DIM, drop)

        self.use_inter = self.ablation != "no_inter_transformer"
        self.tier3 = (InterProceduralTransformer(hidden, inter["hidden"], inter["heads"], inter["layers"],
                                                 len(INTER_TYPES), drop) if self.use_inter else None)
        d_graph = inter["hidden"] if self.use_inter else hidden

        self.use_global = self.ablation != "no_global_features"
        self.pool = "mean" if self.ablation == "pool_mean" else m.get("pool", "max")
        d_head = d_graph + (GLOBAL_FEAT_DIM if self.use_global else 0)
        self.head = nn.Sequential(nn.Linear(d_head, hidden), nn.ReLU(), nn.Dropout(drop), nn.Linear(hidden, 1))

    def set_epoch(self, epoch: int) -> str:
        """Warmup: epoch < warmup_epochs -> E_sem theo luật; sau đó -> học được. Trả chế độ hiện tại."""
        if self.learned_sem:
            self.sem_mode = "rule" if epoch < self.warmup_epochs else "learned"
        return self.sem_mode

    # ------------------------------------------------------------------ E_sem
    @staticmethod
    def rule_edges(batch) -> torch.Tensor:
        """Cạnh luật = seed source->sink tới được (SEM_POS) GIAO tập ứng viên CAND mà predictor thấy.
        Cùng vũ trụ ứng viên với cạnh học được -> so sánh rule_e_sem vs full công bằng khi max_cand
        cắt bớt ứng viên. Khi max_cand không binding, SEM_POS ⊆ CAND nên phép giao = SEM_POS.
        Dùng cho cả ablation rule_e_sem lẫn warmup."""
        rule, cand = batch[SEM_POS].edge_index, batch[CAND].edge_index
        if rule.numel() == 0 or cand.numel() == 0:
            return rule.new_empty(2, 0)
        n = batch[STMT].num_nodes
        return rule[:, torch.isin(rule[0] * n + rule[1], cand[0] * n + cand[1])]

    def _sem_edges(self, batch, h0):
        """Trả (edge_index [2,K], weight [K], taint_logits [|CAND|] hoặc None)."""
        empty = (batch[CAND].edge_index.new_empty(2, 0), h0.new_empty(0), None)
        if self.sem_mode == "none":
            return empty
        if self.sem_mode == "rule":
            rule = self.rule_edges(batch)
            keep = topk_per_dst(rule[1], torch.ones(rule.shape[1], device=rule.device), self.top_k)
            return rule[:, keep], h0.new_ones(int(keep.sum())), None
        cand = batch[CAND].edge_index
        if cand.numel() == 0:
            return empty
        logits = self.taint(h0, cand)
        p = torch.sigmoid(logits)
        keep = self.taint.select_edges(cand, p)
        return cand[:, keep], p[keep], logits

    def _intra_edges(self, batch, sem_ei, sem_w):
        eis, attrs = [], []
        for t_i, name in enumerate(INTRA_TYPES):
            if name == "E_dfg" and self.ablation == "no_e_dfg":
                continue
            if name == "E_sem":
                ei, w = sem_ei, sem_w
            else:
                ei = batch[PYG_EDGE[name]].edge_index
                w = torch.ones(ei.shape[1], device=ei.device)
            a = torch.zeros(ei.shape[1], _E_DIM, device=ei.device)
            a[:, t_i] = 1.0
            a[:, -1] = w
            eis.append(ei); attrs.append(a)
        return torch.cat(eis, 1), torch.cat(attrs, 0)

    def _inter_edges(self, batch, device):
        eis, attrs = [], []
        for t_i, name in enumerate(INTER_TYPES):
            ei = batch[PYG_EDGE[name]].edge_index
            a = torch.zeros(ei.shape[1], len(INTER_TYPES), device=device)
            a[:, t_i] = 1.0
            eis.append(ei); attrs.append(a)
        return torch.cat(eis, 1), torch.cat(attrs, 0)

    # ---------------------------------------------------------------- forward
    def forward(self, batch) -> dict:
        """Trả {'logit': [B], 'taint_loss': scalar, 'n_sem': int, 'taint_logits': [|CAND|] | None}."""
        st = batch[STMT]
        e_tok = self.tier1(st.x_tok)
        h0 = self.stmt_proj(torch.cat([e_tok, st.x], dim=-1))

        sem_ei, sem_w, taint_logits = self._sem_edges(batch, h0)
        ei, ea = self._intra_edges(batch, sem_ei, sem_w)
        h_stmt = self.tier2(h0, ei, ea)

        n_func = batch[FUNC].num_nodes
        in_f = batch[IN_FUNC].edge_index
        h_func = scatter(h_stmt[in_f[0]], in_f[1], dim=0, dim_size=n_func, reduce=self.pool)
        if self.use_inter:
            fei, fea = self._inter_edges(batch, h_func.device)
            h_func = self.tier3(h_func, fei, fea)

        fb = getattr(batch[FUNC], "batch", None)
        if fb is None:                       # một đồ thị đơn, chưa qua DataLoader
            fb = torch.zeros(n_func, dtype=torch.long, device=h_func.device)
        n_graph = int(batch.global_x.shape[0])
        g = scatter(h_func, fb, dim=0, dim_size=n_graph, reduce=self.pool)
        if self.use_global:
            g = torch.cat([g, batch.global_x], dim=-1)
        logit = self.head(g).squeeze(-1)

        if self.learned_sem:
            pos, neg = batch[SEM_POS].edge_index, batch[SEM_NEG].edge_index
            pw = self.taint_pos_weight
            if pw == "auto":
                pw = neg.shape[1] / pos.shape[1] if pos.shape[1] and neg.shape[1] else None
            taint_loss = self.taint.bce_loss(h0, pos, neg, pos_weight=pw)
        else:
            taint_loss = logit.new_zeros(())
        capped = getattr(batch, "cand_capped", None)
        return {"logit": logit, "taint_loss": taint_loss, "n_sem": int(sem_ei.shape[1]), "sem_ei": sem_ei,
                # tỉ lệ đồ thị trong batch có số ứng viên bị max_cand cắt (nan nếu đồ thị cũ thiếu cờ)
                "cand_capped_frac": float(capped.float().mean()) if capped is not None else float("nan"),
                "taint_logits": taint_logits, "h0": h0}
