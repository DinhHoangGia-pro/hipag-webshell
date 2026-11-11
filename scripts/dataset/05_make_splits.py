#!/usr/bin/env python3
"""Bước 11 — Split cluster-disjoint theo group (RQF-05), phân tầng theo (label, source).

* Train pool: mỗi tầng (label, source chiếm đa số trong cụm) — cụm xếp theo kích thước giảm dần (hoà: ngẫu nhiên
  theo seed), gán lần lượt vào split đang thiếu nhiều nhất so với tỉ lệ đích -> tỉ lệ mẫu sát đích, không cụm nào
  nằm hai phía.
* Holdout cross-dataset (role=holdout_cross_dataset): split=holdout, chỉ các cụm không chạm train pool.
Ghi splits.csv (cột: sample_id, path, label, split, source, cluster_id, level, hard, role) + split_summary.json.
06_build_obfuscation_matrix.py sẽ NỐI thêm hàng split=obf — chạy lại 06 sau mỗi lần chạy 05."""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hipag.data.pipeline import read_csv, write_csv  # noqa: E402
from hipag.utils.config import load_config  # noqa: E402

SPLIT_FIELDS = ["sample_id", "path", "label", "split", "source", "cluster_id", "level", "hard", "role"]


def assign_groups(clusters: dict[str, list[dict]], ratios: dict[str, float], rng: random.Random) -> dict[str, str]:
    names = list(ratios)
    total = sum(len(v) for v in clusters.values())
    cur = dict.fromkeys(names, 0)
    keys = list(clusters)
    rng.shuffle(keys)
    keys.sort(key=lambda k: -len(clusters[k]))          # sort ổn định: cùng kích thước giữ thứ tự ngẫu nhiên
    out = {}
    for k in keys:
        s = max(names, key=lambda n: (ratios[n] * total - cur[n]) / ratios[n])
        out[k] = s
        cur[s] += len(clusters[k])
    return out


def main(args):
    cfg = load_config(args.config)
    rows = read_csv(ROOT / cfg["manifest"])
    gstat = {s["sample_id"]: s for s in read_csv(ROOT / cfg["graph_stats"])}
    missing = [r["sample_id"] for r in rows if r["sample_id"] not in gstat]
    if missing:
        raise SystemExit(f"{len(missing)} mẫu chưa có đồ thị (chạy 04 trước): {missing[:5]}")
    gk, hrole = cfg["group_key"], cfg["holdout_role"]

    by_cluster = defaultdict(list)
    for r in rows:
        by_cluster[r[gk]].append(r)
    out, dropped = [], Counter()
    strata = defaultdict(dict)
    for cid, mem in by_cluster.items():
        roles = {m["role"] for m in mem}
        if roles == {hrole}:                       # cụm thuần holdout -> holdout
            out += [{**m, "split": "holdout"} for m in mem]
            continue
        if hrole in roles:                         # cụm lẫn: bỏ phần holdout, phần train_pool đi tiếp
            for m in mem:
                if m["role"] == hrole:
                    dropped[f"holdout_overlap_train/label{m['label']}"] += 1
            mem = [m for m in mem if m["role"] != hrole]
        lab = mem[0]["label"]
        src = Counter(m["source"] for m in mem).most_common(1)[0][0]
        strata[(lab, src)][cid] = mem
    rng = random.Random(cfg["seed"])
    for key in sorted(strata):
        assign = assign_groups(strata[key], cfg["ratios"], rng)
        for cid, mem in strata[key].items():
            for m in mem:
                out.append({**m, "split": assign[cid]})

    for r in out:
        r["path"] = gstat[r["sample_id"]]["graph_path"]
        r["level"] = ""
    out.sort(key=lambda r: (r["split"], r["sample_id"]))
    write_csv(ROOT / cfg["out_csv"], out, SPLIT_FIELDS)

    # kiểm tra cluster-disjoint
    where = defaultdict(set)
    for r in out:
        where[r[gk]].add(r["split"])
    leak = {c: s for c, s in where.items() if len(s) > 1}
    assert not leak, f"cụm nằm nhiều split: {list(leak.items())[:5]}"

    cnt = Counter((r["split"], r["label"]) for r in out)
    summ = {
        "n": len(out), "cluster_disjoint": True,
        "by_split_label": {f"{s}/{l}": c for (s, l), c in sorted(cnt.items())},
        "by_split_source": {f"{s}/{src}": c for (s, src), c in sorted(Counter((r["split"], r["source"]) for r in out).items())},
        "hard_benign_by_split": dict(Counter(r["split"] for r in out if r["label"] == "0" and r["hard"] == "1")),
        "dropped": dict(dropped),
        "ratio_target": cfg["ratios"], "seed": cfg["seed"],
    }
    for s in ("train", "val", "test", "holdout"):
        p, n = cnt[(s, "1")], cnt[(s, "0")]
        summ[f"{s}_pos_frac"] = round(p / max(p + n, 1), 4)
    (ROOT / cfg["out_summary"]).write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
