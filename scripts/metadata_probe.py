#!/usr/bin/env python3
"""Leakage/shortcut probe (chuẩn nhóm, RQF-04/05): chỉ dùng đặc trưng nông/metadata -> RandomForest.

Hai bộ đặc trưng (đánh giá riêng + gộp):
  * shallow : từ byte thô — kích thước, dòng, entropy, tỉ lệ lớp ký tự, chuỗi base64 dài, thẻ PHP, namespace/class,
              docblock, CRLF, BOM... (KHÔNG có tên hàm nguy hiểm — đó là tín hiệu ngữ nghĩa, không phải shortcut).
  * graphmeta: metadata của bước parse/dựng đồ thị — parse status, số statement/hàm/cạnh. Nếu riêng bộ này
              đã phân lớp tốt thì pipeline dựng đồ thị đang rò nhãn qua cấu trúc nông.
Giao thức: pool = train∪val∪test (không holdout/obf); StratifiedGroupKFold(5) theo cluster_id; 5 seed -> mean±sd.
Thêm: fit trên split=train -> đánh giá split=holdout (ngoài phân phối) và từng level obf.
AUC cao bất thường (>= alert_auc) => dataset có shortcut, phải xử lý trước khi tin model."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hipag.data.pipeline import read_csv  # noqa: E402
from hipag.utils.config import load_config  # noqa: E402

DEFAULT_PROBE = {
    "manifest": "experiments/dataset/manifest.csv",
    "obf_manifest": "experiments/dataset/obfuscation_manifest.csv",
    "graph_stats": ["experiments/dataset/graph_stats.csv"],
    "graph_log_obf": "data/features_small/_build_log_obf.jsonl",
    "seeds": [0, 1, 2, 3, 4], "folds": 5, "n_estimators": 300, "alert_auc": 0.90,
    "out_json": "experiments/dataset/metadata_probe.json",
    "out_md": "experiments/dataset/metadata_probe.md",
}

_B64 = re.compile(rb"[A-Za-z0-9+/=]{100,}")
_HEX = re.compile(rb"(?:\\x[0-9a-fA-F]{2}){8,}")
SHALLOW = ["log_size", "n_lines", "avg_line_len", "max_line_len", "entropy", "frac_alpha", "frac_digit",
           "frac_space", "frac_punct", "frac_upper", "frac_nonascii", "n_long_b64", "has_hex_escape",
           "n_php_open", "starts_php_tag", "has_close_tag", "has_inline_html", "has_namespace", "has_class",
           "has_docblock", "frac_comment_lines", "crlf", "has_bom", "n_dollar_per_line", "frac_indented_lines"]
GRAPHMETA = ["status_ok", "status_recovered", "status_fallback", "n_errors", "log_n_stmt_total", "n_stmt",
             "n_func", "n_cfg", "n_dfg", "n_call", "n_includes", "log_n_cand_full", "n_role_src", "n_role_sink",
             "cand_capped", "n_nodes", "has_sem_pair", "has_typed_cand"]   # cand_capped + parse status lệch nhãn (esem_coverage) -> phải có trong probe lối tắt


def shallow_features(b: bytes) -> list[float]:
    n = max(len(b), 1)
    lines = b.split(b"\n")
    ll = [len(x) for x in lines]
    cnt = Counter(b)
    ent = -sum(c / n * math.log2(c / n) for c in cnt.values())
    alpha = sum(cnt[c] for c in range(128) if chr(c).isalpha())
    digit = sum(cnt[c] for c in b"0123456789")
    space = sum(cnt[c] for c in b" \t\r\n")
    upper = sum(cnt[c] for c in range(65, 91))
    nonascii = sum(v for c, v in cnt.items() if c >= 128)
    punct = n - alpha - digit - space - nonascii
    s = b.lstrip(b"\xef\xbb\xbf")
    comment_lines = sum(1 for x in lines if x.lstrip().startswith((b"//", b"#", b"*", b"/*")))
    return [
        math.log1p(len(b)), math.log1p(len(lines)), float(np.mean(ll)), math.log1p(max(ll)), ent,
        alpha / n, digit / n, space / n, punct / n, upper / n, nonascii / n,
        float(len(_B64.findall(b))), float(bool(_HEX.search(b))),
        float(b.lower().count(b"<?php")), float(s[:5].lower() == b"<?php"), float(b"?>" in b),
        float(not s.lstrip().startswith(b"<?")), float(bool(re.search(rb"^\s*namespace\s", b, re.M))),
        float(bool(re.search(rb"^\s*(abstract\s+|final\s+)?class\s", b, re.M))), float(b"/**" in b),
        comment_lines / max(len(lines), 1), float(b"\r\n" in b), float(b.startswith(b"\xef\xbb\xbf")),
        b.count(b"$") / max(len(lines), 1), sum(1 for x in lines if x[:1] in (b" ", b"\t")) / max(len(lines), 1),
    ]


def graphmeta_features(s: dict) -> list[float]:
    st = s["status"]
    f = lambda k: float(s.get(k) or 0)  # noqa: E731
    return [float(st == "ok"), float(st == "recovered"), float(st in ("fallback_tokens", "parser_crash")),
            f("n_errors"), math.log1p(f("n_stmt_total")), f("n_stmt"), f("n_func"), f("n_cfg"), f("n_dfg"),
            f("n_call"), f("n_includes"), math.log1p(f("n_cand_full")), f("n_role_src"), f("n_role_sink"),
            f("cand_capped"), f("n_stmt") + f("n_func"), float(f("n_sem_pos") > 0), float(f("n_typed_pairs") > 0)]


_TOK = re.compile(rb"\w+|[^\w\s]")
# Bộ BẮT BUỘC (chốt PHIÊN DATA): cand_capped, parse_status, độ dài file, số token, entropy, n_nodes, has_sem_pair
REQUIRED = ["cand_capped", "status_ok", "status_recovered", "status_fallback", "log_size", "log_n_tokens",
            "entropy", "n_nodes", "has_sem_pair", "has_typed_cand"]


def scores(y, p) -> dict:
    out = {"acc": accuracy_score(y, p >= 0.5), "f1_macro": f1_score(y, p >= 0.5, average="macro")}
    out["auc"] = roc_auc_score(y, p) if len(set(y)) > 1 else float("nan")
    return out


def msd(xs):
    xs = [x for x in xs if not (isinstance(x, float) and math.isnan(x))]
    return {"mean": float(np.mean(xs)), "sd": float(np.std(xs, ddof=1)) if len(xs) > 1 else 0.0} if xs else None


def main(args):
    cfg = load_config(args.config)
    pc = {**DEFAULT_PROBE, **cfg.get("probe", {})}
    splits = read_csv(ROOT / cfg["splits"])
    man = {r["sample_id"]: r for r in read_csv(ROOT / pc["manifest"])}
    obfm = {r["sample_id"]: r for r in read_csv(ROOT / pc["obf_manifest"])} if (ROOT / pc["obf_manifest"]).exists() else {}
    gst = {}
    for g in pc["graph_stats"]:
        gst.update({s["sample_id"]: s for s in read_csv(ROOT / g)})
    if (ROOT / pc["graph_log_obf"]).exists():
        for ln in (ROOT / pc["graph_log_obf"]).read_text().splitlines():
            if ln.strip():
                s = json.loads(ln); gst[s["sample_id"]] = s

    def raw_path(r):
        return ROOT / (obfm[r["sample_id"]]["php_path"] if r["split"] == "obf" else man[r["sample_id"]]["path"])

    # Đặc trưng nông đo trên bản CHUẨN HOÁ (tools/php/canon_lib.php) — đúng bản model thấy (chốt 2026-11-07).
    import base64
    from hipag.parsing.php_ast import canonicalize_batch
    paths = [raw_path(r) for r in splits]
    raws = [base64.b64decode(c) if c is not None else p.read_bytes()
            for c, p in zip(canonicalize_batch(paths), paths)]
    X_sh = np.array([shallow_features(b) for b in raws])
    X_gm = np.array([graphmeta_features(gst[r["sample_id"]]) for r in splits])
    y = np.array([int(r["label"]) for r in splits])
    sp = np.array([r["split"] for r in splits])
    lv = np.array([r["level"] for r in splits])
    groups = np.array([r["cluster_id"] for r in splits])
    ntok = np.array([[math.log1p(len(_TOK.findall(b)))] for b in raws])
    allX = np.hstack([X_sh, X_gm, ntok]); alln = SHALLOW + GRAPHMETA + ["log_n_tokens"]
    col = lambda ns: allX[:, [alln.index(n) for n in ns]]  # noqa: E731
    REQ_NOSEM = [n for n in REQUIRED if n not in ("has_sem_pair", "has_typed_cand")]
    sets = {"required": col(REQUIRED), "required_no_sem": col(REQ_NOSEM),
            "shallow": X_sh, "graphmeta": X_gm, "all": allX}
    names = {"required": REQUIRED, "required_no_sem": REQ_NOSEM,
             "shallow": SHALLOW, "graphmeta": GRAPHMETA, "all": alln}

    pool = np.isin(sp, ["train", "val", "test"])
    res = {"protocol": {**{k: pc[k] for k in ("seeds", "folds", "n_estimators", "alert_auc")},
                        "pool_n": int(pool.sum()), "pool_pos_frac": float(y[pool].mean()),
                        "cv": "StratifiedGroupKFold by cluster_id on train+val+test",
                        "transfer": "fit split=train -> eval split=holdout and split=obf per level"},
           "results": {}}
    for name, X in sets.items():
        cv_runs, tr_runs, imps = [], {}, []
        for seed in pc["seeds"]:
            skf = StratifiedGroupKFold(n_splits=pc["folds"], shuffle=True, random_state=seed)
            Xp, yp, gp = X[pool], y[pool], groups[pool]
            oof = np.zeros(len(yp))
            for tr, te in skf.split(Xp, yp, gp):
                m = RandomForestClassifier(n_estimators=pc["n_estimators"], random_state=seed, n_jobs=-1,
                                           class_weight="balanced").fit(Xp[tr], yp[tr])
                oof[te] = m.predict_proba(Xp[te])[:, 1]
            cv_runs.append(scores(yp, oof))
            trm = sp == "train"
            m = RandomForestClassifier(n_estimators=pc["n_estimators"], random_state=seed, n_jobs=-1,
                                       class_weight="balanced").fit(X[trm], y[trm])
            imps.append(m.feature_importances_)
            evals = {"test": sp == "test", "holdout": sp == "holdout"}
            for L in sorted(set(lv[sp == "obf"])):
                # mỗi level obf nay có CẢ HAI lớp (06 labels:[0,1]) -> AUC per-level đo đúng boundary
                evals[f"obf_{L}"] = (sp == "obf") & (lv == L)
            for k, msk in evals.items():
                if msk.sum():
                    tr_runs.setdefault(k, []).append(scores(y[msk], m.predict_proba(X[msk])[:, 1]))
        imp = np.mean(imps, axis=0)
        top = sorted(zip(names[name], imp), key=lambda t: -t[1])[:8]
        res["results"][name] = {
            "group_cv": {k: msd([r[k] for r in cv_runs]) for k in ("auc", "acc", "f1_macro")},
            "train_to": {ev: {k: msd([r[k] for r in runs]) for k in ("auc", "acc", "f1_macro")}
                         for ev, runs in tr_runs.items()},
            "top_importance": [(n, round(float(v), 4)) for n, v in top],
        }
    res["alert_by_set"] = {k: bool(v["group_cv"]["auc"]["mean"] >= pc["alert_auc"]) for k, v in res["results"].items()}
    res["alert"] = res["alert_by_set"]["required"]   # CỔNG: bộ bắt buộc
    (ROOT / pc["out_json"]).write_text(json.dumps(res, indent=2))

    f = lambda d: "—" if d is None else f"{d['mean']:.3f}±{d['sd']:.3f}"  # noqa: E731
    md = ["# Metadata / shortcut probe (RQF-04/05)", "",
          f"[đặc trưng trên mã CHUẨN HOÁ] Pool train+val+test n={res['protocol']['pool_n']} (pos={res['protocol']['pool_pos_frac']:.3f}); "
          f"RF {pc['n_estimators']} cây, class_weight=balanced; {len(pc['seeds'])} seed; "
          f"StratifiedGroupKFold({pc['folds']}) theo cluster_id.", "",
          "| feature set | eval | AUC | Acc | macro-F1 |", "|---|---|---|---|---|"]
    for name, r in res["results"].items():
        md.append(f"| {name} | group-CV | {f(r['group_cv']['auc'])} | {f(r['group_cv']['acc'])} | {f(r['group_cv']['f1_macro'])} |")
        for ev, d in r["train_to"].items():
            md.append(f"| {name} | train→{ev} | {f(d['auc'])} | {f(d['acc'])} | {f(d['f1_macro'])} |")
    md += ["", "Top importance (fit trên train, trung bình seed):"]
    for name, r in res["results"].items():
        md.append(f"- **{name}**: " + ", ".join(f"{n} {v}" for n, v in r["top_importance"]))
    md += ["", f"Alert theo bộ (group-CV AUC ≥ {pc['alert_auc']}): {res['alert_by_set']}",
           f"**CỔNG (bộ required): ALERT = {res['alert']}**"]
    (ROOT / pc["out_md"]).write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
