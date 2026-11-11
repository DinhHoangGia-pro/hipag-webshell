#!/usr/bin/env python3
"""Bước 13–14 — PHP -> đồ thị phân cấp (statement/function/file; seq/skip/cfg/dfg/call + cặp ứng viên/luật E_sem)
-> PyG HeteroData, mỗi mẫu một file .pt trong data/features_small/<2hex>/<sample_id>.pt.

Builder CHỈ dựng đồ thị + lưu cặp ứng viên (cand) và cặp luật (sem_pos/sem_neg) + n_cand_full/cand_capped;
E_sem do model/hipag.py sinh lúc forward. Resume: bỏ qua mẫu đã có .pt và dòng log.
Mẫu parse lỗi KHÔNG bị loại: status recovered/fallback_tokens/parser_crash ghi vào parse_fail.csv (RQF-05)."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hipag.data.build import STAT_FIELDS, run_build  # noqa: E402
from hipag.data.pipeline import read_csv, write_csv  # noqa: E402
from hipag.utils.config import load_config  # noqa: E402


def main(args):
    cfg = load_config(args.config)
    rows = read_csv(ROOT / cfg["manifest"])
    stats = run_build(rows, cfg, ROOT / cfg["out_small_dir"] / "_build_log.jsonl")
    write_csv(ROOT / cfg["out_stats"], stats, STAT_FIELDS)
    fails = [s for s in stats if s["status"] != "ok"]
    write_csv(ROOT / cfg["out_parse_fail"], fails,
              ["sample_id", "label", "source", "path", "status", "parser", "n_errors", "error"])
    by = Counter((s["status"], s["label"]) for s in stats)
    print("status x label:", dict(sorted(by.items())))
    S = lambda k: sum(int(s.get(k) or 0) for s in stats)  # noqa: E731
    print(f"E_sem: bridge liên thủ tục {S('n_bridged_crossfn')} cặp; arg->param: CHÍNH XÁC "
          f"{S('n_bridged_arg_carried')} + FALLBACK {S('n_bridged_fallback')}; return->callsite: CHÍNH XÁC "
          f"{S('n_bridged_return_exact')} + FALLBACK {S('n_bridged_return_fallback')} "
          f"(fallback = dump thiếu callargs/params, vd fallback_tokens); "
          f"cap: {S('cand_capped')} đồ thị chạm cap, cặp source->sink bị cắt {S('n_typed_cut')} (phải ~0)")
    reasons = Counter(k for s in stats for kv in (s.get("deobf_skip_reasons") or "").split("|") if kv
                      for k in [kv.split(":")[0]] for _ in range(int(kv.split(":")[1])))
    print(f"UPG-02 giải vỏ tĩnh: fold {S('n_deobf_folded')}, ghép mã {S('n_deobf_grafted')} "
          f"({sum(1 for s in stats if int(s.get('n_deobf_grafted') or 0))} file, {S('n_deobf_stmts')} statement), "
          f"bỏ qua {S('n_deobf_skipped')}: {dict(reasons)}")
    print(f"-> {len(stats)} đồ thị trong {cfg['out_small_dir']}; parse không sạch: {len(fails)} "
          f"(ghi {cfg['out_parse_fail']})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
