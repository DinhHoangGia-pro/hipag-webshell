#!/usr/bin/env python3
"""Tập con KHÓ khớp-ký-tự (validation RQF-04): webshell CÓ CẤU TRÚC (đã giải vỏ, n_stmt>=min) ghép 1-1 với benign
nearest-neighbor trên ĐẶC TRƯNG KÝ TỰ (entropy, frac_digit, log_size, base64-presence) — KHÔNG ghép theo taint/đồ thị.
Mục tiêu: trên tập con này đặc trưng nông/ký tự KHÔNG tách được lớp (shallow AUC ~ ngẫu nhiên) -> detector buộc dùng
cấu trúc/ngữ nghĩa. Đặc trưng tính trên mã CHUẨN HOÁ (canon_lib.php) — đúng bản model thấy.

  python scripts/analysis/char_matched_subset.py [--caliper 0.5] [--min-stmt 3]
CỔNG: shallow AUC <= 0.60.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neighbors import NearestNeighbors

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from hipag.data.pipeline import read_csv  # noqa: E402
from hipag.parsing.php_ast import canonicalize_batch  # noqa: E402
from metadata_probe import SHALLOW, shallow_features  # noqa: E402

import re  # noqa: E402
import torch  # noqa: E402

_B64 = re.compile(rb"[A-Za-z0-9+/=]{100,}")


def char4(b: bytes) -> list[float]:
    """4 trục khớp: entropy byte, frac_digit, log_size, base64-presence (log1p số blob base64 dài)."""
    n = max(len(b), 1)
    from collections import Counter
    c = Counter(b)
    ent = -sum(v / n * math.log2(v / n) for v in c.values())
    digit = sum(c[d] for d in b"0123456789") / n
    return [ent, digit, math.log1p(len(b)), math.log1p(len(_B64.findall(b)))]


def graph_structure(graph_relpath: str, graph_root: Path) -> tuple[float, float]:
    graph_path = graph_root / graph_relpath
    graph = torch.load(graph_path, weights_only=False)
    n_nodes = sum(int(graph[node_type].num_nodes) for node_type in graph.node_types)
    excluded = {"cand", "sem_pos", "sem_neg", "rule_src_sink"}
    n_edges = sum(int(graph[rel].edge_index.shape[1]) for rel in graph.edge_types
                  if rel[1] not in excluded)
    return float(n_nodes), float(n_edges)


def main(a):
    splits = [r for r in read_csv(ROOT / a.splits) if r["split"] in ("train", "val", "test")]
    man = {r["sample_id"]: r for r in read_csv(ROOT / a.manifest)}
    gst = {r["sample_id"]: r for r in read_csv(ROOT / a.graph_stats)}
    paths = [ROOT / man[r["sample_id"]]["path"] for r in splits]
    canon = canonicalize_batch(paths)
    raws = [base64.b64decode(c) if c is not None else p.read_bytes() for c, p in zip(canon, paths)]
    X4 = np.array([char4(b) for b in raws])
    Xsh = np.array([shallow_features(b) for b in raws])
    graph_root = ROOT / "data/features_small"
    graph_struct = np.array([graph_structure(r["path"], graph_root) for r in splits])
    y = np.array([int(r["label"]) for r in splits])
    grp = np.array([r["cluster_id"] for r in splits])

    def nstmt(r):
        return int(gst.get(r["sample_id"], {}).get("n_stmt", 0) or 0)
    struct = np.array([nstmt(r) >= a.min_stmt for r in splits])
    nstmt_values = np.array([nstmt(r) for r in splits])
    wi = np.where((y == 1) & struct)[0]          # webshell có cấu trúc
    bi = np.where(y == 0)[0]                      # benign (mọi)
    if a.match_structure:
        match_x = Xsh
        mu, sd = match_x.mean(0), match_x.std(0) + 1e-9
        Z = (match_x - mu) / sd
    elif a.match_all_shallow:
        mu, sd = Xsh.mean(0), Xsh.std(0) + 1e-9
        Z = (Xsh - mu) / sd
    else:
        mu, sd = X4.mean(0), X4.std(0) + 1e-9
        Z = (X4 - mu) / sd

    # 1-1 nearest-neighbor: với mỗi webshell lấy K benign gần nhất -> gộp -> gán tham lam theo khoảng cách, có caliper
    k = min(60, len(bi))
    nn = NearestNeighbors(n_neighbors=k).fit(Z[bi])
    dist, idx = nn.kneighbors(Z[wi])
    cand = sorted((dist[r, c], int(wi[r]), int(bi[idx[r, c]])) for r in range(len(wi)) for c in range(k))
    usedw, usedb, pairs = set(), set(), []
    for d, w, bb in cand:
        if d > a.caliper or w in usedw or bb in usedb:
            continue
        usedw.add(w); usedb.add(bb); pairs.append((w, bb, d))
    sub = sorted([w for w, _, _ in pairs] + [b for _, b, _ in pairs])
    ys, gs, Xs = y[sub], grp[sub], Xsh[sub]

    # shallow probe trên tập con
    aucs = []
    for seed in a.seeds:
        oof = np.zeros(len(ys))
        nsp = min(5, int(min(np.bincount(ys))), len(set(gs)))
        for tr, te in StratifiedGroupKFold(n_splits=max(2, nsp), shuffle=True, random_state=seed).split(Xs, ys, gs):
            m = RandomForestClassifier(300, random_state=seed, n_jobs=-1, class_weight="balanced").fit(Xs[tr], ys[tr])
            oof[te] = m.predict_proba(Xs[te])[:, 1]
        aucs.append(roc_auc_score(ys, oof))
    auc_m, auc_s = float(np.mean(aucs)), float(np.std(aucs, ddof=1))

    gm_features = []
    for i in sub:
        s = gst[splits[i]["sample_id"]]
        st = s.get("status", "")
        n_nodes = graph_struct[i, 0]
        n_edges = graph_struct[i, 1]
        gm_features.append([
            float(st == "ok"), float(st == "recovered"), float(st in ("fallback_tokens", "parser_crash")),
            float(s.get("n_errors") or 0), math.log1p(nstmt(splits[i])), float(s.get("n_func") or 0),
            float(s.get("n_cfg") or 0), float(s.get("n_dfg") or 0), float(s.get("n_call") or 0),
            float(s.get("n_includes") or 0), math.log1p(n_nodes), math.log1p(n_edges),
        ])
    gm = np.array(gm_features)
    gm_aucs = []
    for seed in a.seeds:
        oof = np.zeros(len(ys))
        nsp = min(5, int(min(np.bincount(ys))), len(set(gs)))
        for tr, te in StratifiedGroupKFold(n_splits=max(2, nsp), shuffle=True, random_state=seed).split(gm, ys, gs):
            m = RandomForestClassifier(300, random_state=seed, n_jobs=-1, class_weight="balanced").fit(gm[tr], ys[tr])
            oof[te] = m.predict_proba(gm[te])[:, 1]
        gm_aucs.append(roc_auc_score(ys, oof))
    gm_auc_m, gm_auc_s = float(np.mean(gm_aucs)), float(np.std(gm_aucs, ddof=1))

    def dist4(mask):
        return {n: [round(float(X4[mask, j].mean()), 3), round(float(X4[mask, j].std()), 3)]
                for j, n in enumerate(["entropy", "frac_digit", "log_size", "log_b64_blobs"])}
    def dist_struct(mask):
        values = np.column_stack([nstmt_values, graph_struct])
        selected = values[mask]
        return {n: [round(float(selected[:, j].mean()), 3), round(float(selected[:, j].std()), 3)]
                for j, n in enumerate(["n_stmt", "n_nodes", "n_edges"])}
    wmask = np.array([i in usedw for i in range(len(splits))])
    bmask = np.array([i in usedb for i in range(len(splits))])
    res = {
        "min_stmt": a.min_stmt, "caliper": a.caliper,
        "n_webshell_structured_pool": int(len(wi)), "n_benign_pool": int(len(bi)),
        "n_pairs": len(pairs), "subset_size": len(sub),
        "match_dist": {"mean": round(float(np.mean([d for *_, d in pairs])), 4),
                       "p90": round(float(np.quantile([d for *_, d in pairs], 0.9)), 4)} if pairs else None,
        "shallow_auc_subset": {"mean": round(auc_m, 4), "sd": round(auc_s, 4)},
        "graphmeta_auc_subset": {"mean": round(gm_auc_m, 4), "sd": round(gm_auc_s, 4)},
        "gate_pass": bool(auc_m <= a.gate and gm_auc_m <= a.gate and len(sub) >= 120),
        "char_dist_webshell": dist4(wmask), "char_dist_benign": dist4(bmask),
        "char_dist_full_webshell": dist4((y == 1) & struct), "char_dist_full_benign": dist4(y == 0),
        "struct_dist_webshell": dist_struct(wmask), "struct_dist_benign": dist_struct(bmask),
        "clusters_in_subset": int(len(set(gs))),
    }
    subset_out = ROOT / a.out_subsets
    subset_out.parent.mkdir(parents=True, exist_ok=True)
    from hipag.data.pipeline import write_csv
    write_csv(subset_out, [
        {**splits[w], "pair_id": i, "match_role": "webshell", "match_distance": d}
        for i, (w, b, d) in enumerate(pairs)
    ] + [
        {**splits[b], "pair_id": i, "match_role": "benign", "match_distance": d}
        for i, (w, b, d) in enumerate(pairs)
    ], list(splits[0].keys()) + ["pair_id", "match_role", "match_distance"])
    res["matching"] = "char4_structure_normalized" if a.match_structure else (
        "all_shallow_normalized" if a.match_all_shallow else "char4")
    res["subset_csv"] = str(a.out_subsets)
    (ROOT / a.out).write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    print(f"\nCỔNG shallow AUC <= {a.gate}: {'ĐẠT' if res['gate_pass'] else 'CHƯA ĐẠT'} "
          f"(AUC={auc_m:.3f}±{auc_s:.3f}, n={len(sub)}, {len(pairs)} cặp)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", default="experiments/dataset/splits.csv")
    ap.add_argument("--manifest", default="experiments/dataset/manifest.csv")
    ap.add_argument("--graph-stats", dest="graph_stats", default="experiments/dataset/graph_stats.csv")
    ap.add_argument("--min-stmt", dest="min_stmt", type=int, default=3)
    ap.add_argument("--caliper", type=float, default=0.5, help="khoảng cách z tối đa cho 1 cặp")
    ap.add_argument("--gate", type=float, default=0.60)
    ap.add_argument("--match-all-shallow", action="store_true",
                    help="match trên toàn bộ shallow features thay vì chỉ 4 trục ký tự")
    ap.add_argument("--match-structure", action="store_true",
                    help="thêm n_stmt, n_nodes và n_edges vào matching ký tự")
    ap.add_argument("--out-subsets", default="experiments/dataset/char_matched_subset.csv")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--out", default="experiments/dataset/char_matched_subset.json")
    main(ap.parse_args())
