#!/usr/bin/env python3
"""Bước 9 — Lấy mẫu benign + subset 'hard benign' (RQF-04). Thủ tục (khai trong collect.yaml):
  * mỗi nguồn benign thường: lấy ngẫu nhiên đều, không hoàn lại, tối đa benign_sampling.per_source_max file PHP
    (seed cố định); danh sách file trước lấy mẫu được sắp xếp theo đường dẫn -> tái lập được;
  * hard_benign: lấy toàn bộ;
  * hard=1 cho mọi file benign khớp hard_regex (có sink/decoder) — subset để đo FPR riêng.
Ghi hàng label=0 vào manifest_raw.csv và experiments/dataset/class_ratio.json (trước dedup)."""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hipag.data.pipeline import read_csv  # noqa: E402
from hipag.utils.config import load_config  # noqa: E402

_spec = importlib.util.spec_from_file_location("collect01", Path(__file__).with_name("01_collect_webshells.py"))
c01 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(c01)


def main_pool(cfg):
    """Benign foil KHÓ (khối benign_pool) — xem src/hipag/data/benign_pool.py."""
    from hipag.data import benign_pool as bp
    from hipag.data.pipeline import sha1_bytes
    pc, filt = cfg["benign_pool"], cfg["php_filter"]
    rx_hard, rx_bd = re.compile(cfg["hard_regex"], re.I), re.compile(pc["backdoor_regex"], re.I)
    print("[02] quét pool benign (trong RAM)...", flush=True)
    pool, excl = bp.scan_pool(pc, filt, rx_hard, rx_bd)

    man = read_csv(ROOT / cfg["out_manifest"])
    ws = [r for r in man if r["label"] == "1"]
    ws_sha = {r["raw_sha1"] for r in ws}
    seen, ok = set(), []
    for r in pool:
        why = ("backdoor_pattern" if r["backdoor"] else "same_bytes_as_webshell" if r["raw_sha1"] in ws_sha
               else "dup_in_pool" if r["raw_sha1"] in seen else "")
        r["excluded"] = why
        seen.add(r["raw_sha1"])
        if not why:
            ok.append(r)
    bd = [r for r in pool if r["excluded"] == "backdoor_pattern"]
    from hipag.data.pipeline import write_csv
    write_csv(ROOT / "experiments/dataset/benign_backdoor_review.csv", bd,
              ["source", "archive", "member", "backdoor_match", "size"])
    ref = {}
    for r in ws:
        if r["role"] == "train_pool" and r["raw_sha1"] not in ref:
            b = (ROOT / r["path"]).read_bytes()
            ref[r["raw_sha1"]] = {"log10_size": __import__("math").log10(max(len(b), 1)), "entropy": bp.entropy(b)}
    sel, info = bp.select(ok, list(ref.values()), pc)
    print(f"[02] pool {len(pool)} -> hợp lệ {len(ok)} -> chọn {len(sel)}; loại "
          f"{dict(Counter(r['excluded'] for r in pool if r['excluded']))}", flush=True)
    bp.extract(sel, pc)
    var = bp.make_variants(sel, pc)
    bp.write_pool_csv(ROOT / "experiments/dataset/benign_pool.csv", pool, {id(r) for r in sel})

    rows = []
    for r in sel:
        key = r["path"] if r["kind"] == "disk" and r["variant"] == "original" else f"{r['archive']}::{r['member']}"
        rows.append({"sample_id": f"{r['source']}_{sha1_bytes(key.encode())[:12]}", "label": 0,
                     "source": r["source"], "year": "", "role": "train_pool", "path": r["path"],
                     "ext": Path(r["member"]).suffix.lower().lstrip("."), "size": r["size"],
                     "raw_sha1": r["raw_sha1"], "hard": r["hard"], "hard_reason": r["hard_reason"],
                     "axis": r["axis"], "variant": r["variant"]})
    hsrc = pc["holdout_existing"]
    hr, he = c01.scan_source({**hsrc, "role": "holdout_cross_dataset"}, 0, filt, hard_rx=rx_hard)
    for x in hr:
        x["axis"], x["variant"] = "holdout", "original"
    c01.merge_out(cfg, rows + hr, excl + he, label=0)

    lab = Counter(int(x["label"]) for x in read_csv(ROOT / cfg["out_manifest"]))
    per = Counter(r["source"] for r in rows)
    stats = {s: {"available": sum(1 for r in ok if r["source"] == s), "selected": per[s],
                 "hard": sum(r["hard"] for r in rows if r["source"] == s),
                 "axis": next(r["axis"] for r in rows if r["source"] == s)} for s in sorted(per)}
    ratio = {"stage": "raw (truoc dedup) — benign foil KHÓ", "per_source": stats, "holdout_benign": len(hr),
             "variants": dict(var), "n_webshell": lab[1], "n_benign": lab[0],
             "benign_train_pool": len(rows), "hard_frac_train_pool": round(sum(r["hard"] for r in rows) / len(rows), 3),
             "by_axis": dict(Counter(r["axis"] for r in rows)), "procedure": {k: v for k, v in pc.items()
                                                                          if k not in ("existing",)},
             "density": info}
    (ROOT / "experiments/dataset/class_ratio.json").write_text(json.dumps(ratio, indent=2, ensure_ascii=False))
    for k, v in stats.items():
        print(f"  {k:16s} {v}")
    print(f"-> benign train_pool={len(rows)} (hard {ratio['hard_frac_train_pool']:.1%}, axis {ratio['by_axis']}, "
          f"variants {dict(var)}); holdout benign={len(hr)}; webshell={lab[1]}; backdoor loại={len(bd)}")


def main(args):
    cfg = load_config(args.config)
    if "benign_pool" in cfg:
        return main_pool(cfg)
    rx = re.compile(cfg["hard_regex"], re.I)
    samp = cfg["benign_sampling"]
    rows, excl, stats = [], [], {}
    for src in cfg["benign_sources"]:
        r, e = c01.scan_source(src, 0, cfg["php_filter"], hard_rx=rx)
        n_all, cap = len(r), src.get("max", samp["per_source_max"])
        if len(r) > cap:
            r = random.Random(f"{samp['seed']}:{src['name']}").sample(r, cap)
            r.sort(key=lambda x: x["path"])
        stats[src["name"]] = {"available": n_all, "sampled": len(r), "hard": sum(x["hard"] for x in r),
                              "role": src.get("role", "train_pool")}
        rows += r; excl += e
    for src in cfg.get("hard_benign", []):
        r, e = c01.scan_source(src, 0, cfg["php_filter"], hard_rx=rx, role="train_pool")
        for x in r:
            x["hard_reason"] = x["hard_reason"] or "hard_source"
            x["hard"] = 1
        stats[src["name"]] = {"available": len(r), "sampled": len(r), "hard": len(r), "hard_source": True}
        rows += r; excl += e
    c01.merge_out(cfg, rows, excl, label=0)

    man = read_csv(ROOT / cfg["out_manifest"])
    lab = Counter(int(x["label"]) for x in man)
    ratio = {"stage": "raw (truoc dedup)", "per_source": stats,
             "n_webshell": lab[1], "n_benign": lab[0],
             "benign_per_webshell": round(lab[0] / max(lab[1], 1), 3),
             "procedure": cfg["benign_sampling"], "hard_regex": cfg["hard_regex"]}
    out = ROOT / "experiments/dataset/class_ratio.json"
    out.write_text(json.dumps(ratio, indent=2, ensure_ascii=False))
    for k, v in stats.items():
        print(f"{k:12s} {v}")
    print(f"-> benign={lab[0]} webshell={lab[1]} (benign/webshell={ratio['benign_per_webshell']}); "
          f"hard={sum(x['hard'] for x in rows)}; loại {len(excl)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
