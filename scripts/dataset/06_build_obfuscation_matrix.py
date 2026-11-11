#!/usr/bin/env python3
"""Bước 16 — Ma trận obfuscation held-out (RQ2/K2): biến đổi giữ-ngữ-nghĩa các mẫu split=test theo level L0..L5,
dựng đồ thị, NỐI hàng split=obf (cột level) vào splits.csv. KHÔNG dùng để train.

Idempotent: xoá hàng split=obf cũ trong splits.csv trước khi nối. Kiểm tra `php -l` cho bản gốc và bản biến đổi;
hàng bị loại chỉ khi biến đổi làm hỏng một file vốn lint sạch (ghi trong obfuscation_manifest.csv)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hipag.data.build import run_build  # noqa: E402
from hipag.data.pipeline import read_csv, rel, write_csv  # noqa: E402
from hipag.parsing.php_ast import PHP_FLAGS  # noqa: E402
from hipag.utils.config import load_config  # noqa: E402

SPLIT_FIELDS = ["sample_id", "path", "label", "split", "source", "cluster_id", "level", "hard", "role"]


def lint(p: str) -> bool:
    r = subprocess.run(["php", "-d", "short_open_tag=1", "-l", p], capture_output=True, timeout=60)
    return r.returncode == 0


def main(args):
    cfg = load_config(args.config)
    gcfg = load_config(cfg["graphs"])
    splits_p = ROOT / cfg["source_webshells"]
    splits = [r for r in read_csv(splits_p) if r["split"] != "obf"]
    man = {r["sample_id"]: r for r in read_csv(ROOT / cfg["manifest"])}
    labels = {str(x) for x in cfg["labels"]}
    base = [r for r in splits if r["split"] == cfg["source_split"] and r["label"] in labels]
    levels = [lv["id"] for lv in cfg["levels"]]
    print(f"nguồn: {len(base)} mẫu split={cfg['source_split']} x {len(levels)} level")

    out_dir = ROOT / cfg["out_dir"]
    jobs = []
    for r in base:
        src = ROOT / man[r["sample_id"]]["path"]
        h = r["sample_id"].rsplit("_", 1)[-1][:2]
        for lv in levels:
            jobs.append((lv, str(src), str(out_dir / lv / h / f"{r['sample_id']}__{lv}.php"), r))

    # 1) biến đổi (PHP, theo chunk song song)
    def run(ch):
        inp = "".join(f"{lv}\t{s}\t{o}\n" for lv, s, o, _ in ch)
        p = subprocess.run(["php", *PHP_FLAGS, str(ROOT / "tools/php/obfuscate.php")], input=inp,
                           capture_output=True, text=True)
        res = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
        if len(res) != len(ch):
            raise RuntimeError(f"obfuscate.php lệch dòng: {p.stderr[-400:]}")
        return res
    chunks = [jobs[i:i + 200] for i in range(0, len(jobs), 200)]
    with ThreadPoolExecutor(cfg.get("workers", 8)) as ex:
        tres = [x for res in ex.map(run, chunks) for x in res]

    # 2) lint gốc + bản biến đổi
    with ThreadPoolExecutor(cfg.get("workers", 8)) as ex:
        lint_orig = dict(zip([str(ROOT / man[r["sample_id"]]["path"]) for r in base],
                             ex.map(lint, [str(ROOT / man[r["sample_id"]]["path"]) for r in base])))
        lint_obf = list(ex.map(lambda j: lint(j[2]) if Path(j[2]).exists() else False, jobs))

    om, rows_build, new_split = [], [], []
    for (lv, s, o, r), tr, lo in zip(jobs, tres, lint_obf):
        lorig = lint_orig[s]
        keep = bool(tr["ok"]) and (lo or not lorig)
        sid = f"{r['sample_id']}__{lv}"
        om.append({"sample_id": sid, "base_sample_id": r["sample_id"], "level": lv, "label": r["label"],
                   "source": r["source"], "transform_ok": int(bool(tr["ok"])), "lint_orig": int(lorig),
                   "lint_obf": int(lo), "n_dyncall": tr.get("n_dyncall", 0), "keep": int(keep),
                   "php_path": rel(o) if tr["ok"] else ""})
        if keep:
            rows_build.append({"sample_id": sid, "label": r["label"], "source": r["source"], "path": rel(o)})
            new_split.append({**r, "sample_id": sid, "split": "obf", "level": lv, "role": "obf_of_test"})
    write_csv(ROOT / cfg["out_manifest"], om, list(om[0].keys()))

    # 3) dựng đồ thị (cùng tham số 04), ghi vào features_small
    stats = run_build(rows_build, gcfg, ROOT / gcfg["out_small_dir"] / "_build_log_obf.jsonl", label="obf")
    gp = {s["sample_id"]: s for s in stats}
    for r in new_split:
        r["path"] = gp[r["sample_id"]]["graph_path"]
    write_csv(splits_p, splits + new_split, SPLIT_FIELDS)

    summ = {
        "n_base": len(base), "levels": levels, "n_rows_obf": len(new_split),
        "by_level_label": {f"{k[0]}/{k[1]}": v for k, v in sorted(Counter((r["level"], r["label"]) for r in new_split).items())},
        "dropped_broken_by_transform": {f"{k[0]}/{k[1]}": v for k, v in
                                        sorted(Counter((x["level"], x["label"]) for x in om if not x["keep"]).items())},
        "lint_orig_fail": sum(1 for v in lint_orig.values() if not v),
        "parse_status_by_level": {f"{k[0]}/{k[1]}": v for k, v in sorted(
            Counter((s["sample_id"].rsplit("__", 1)[1], s["status"]) for s in stats).items())},
    }
    (ROOT / "experiments/dataset/obfuscation_summary.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
