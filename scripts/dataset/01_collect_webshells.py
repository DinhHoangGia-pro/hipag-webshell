#!/usr/bin/env python3
"""Bước 8 — Thu thập + gộp nhãn webshell từ các nguồn (configs/dataset/collect.yaml), lọc PHP.

Ghi experiments/dataset/manifest_raw.csv (hàng label=1; hàng benign do 02 thêm) và excluded_raw.csv
(file đuôi PHP bị loại + lý do). Trùng lặp CHƯA xử lý ở đây (03_dedup_cluster.py)."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hipag.data.pipeline import (MANIFEST_FIELDS, iter_php_files, read_csv, rel, sha1_bytes,  # noqa: E402
                                 write_csv)
from hipag.utils.config import load_config  # noqa: E402


def scan_source(src: dict, label: int, filt: dict, hard_rx=None, role: str | None = None):
    rows, excl = [], []
    root = ROOT / src["path"]
    if not root.exists():
        print(f"[WARN] nguồn {src['name']}: không thấy {root} — bỏ qua")
        return rows, excl
    for p, why in iter_php_files(root, filt):
        rp = rel(p)
        if why:
            excl.append({"source": src["name"], "path": rp, "reason": why})
            continue
        b = p.read_bytes()
        hard, reason = 0, ""
        if hard_rx is not None:
            m = hard_rx.search(b.decode("utf-8", "replace"))
            if m:
                hard, reason = 1, m.group(0).strip()[:40]
        rows.append({
            "sample_id": f"{src['name']}_{sha1_bytes(rp.encode())[:12]}",
            "label": label, "source": src["name"], "year": src.get("year", ""),
            "role": role or src.get("role", "train_pool"), "path": rp, "ext": p.suffix.lower().lstrip("."),
            "size": len(b), "raw_sha1": sha1_bytes(b), "hard": hard, "hard_reason": reason,
        })
    return rows, excl


def merge_out(cfg: dict, rows: list[dict], excl: list[dict], label: int) -> None:
    """Ghi đè phần của `label` trong manifest_raw/excluded_raw, giữ phần của nhãn kia (01 và 02 độc lập)."""
    man, exc = ROOT / cfg["out_manifest"], ROOT / cfg["out_excluded"]
    keep = [r for r in read_csv(man) if int(r["label"]) != label] if man.exists() else []
    write_csv(man, keep + rows, MANIFEST_FIELDS)
    keep_e = [r for r in read_csv(exc) if r.get("label") != str(label)] if exc.exists() else []
    for e in excl:
        e["label"] = label
    write_csv(exc, keep_e + excl, ["label", "source", "path", "reason"])


def main(args):
    cfg = load_config(args.config)
    rows, excl = [], []
    for src in cfg["webshell_sources"]:
        r, e = scan_source(src, 1, cfg["php_filter"])
        rows += r; excl += e
        print(f"{src['name']:12s} role={src.get('role', 'train_pool'):22s} php={len(r):5d} excluded={len(e)}")
    merge_out(cfg, rows, excl, label=1)
    print(f"-> {cfg['out_manifest']}: {len(rows)} webshell; loại {len(excl)} ({dict(Counter(x['reason'] for x in excl))})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
