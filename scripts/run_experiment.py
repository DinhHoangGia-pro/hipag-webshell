#!/usr/bin/env python3
"""Chạy một RQ với N seed (× các biến thể ablation), gộp mean±sd, xuất numbers.tex (RQF-07/09/10).

Ví dụ:
  python scripts/run_experiment.py --config configs/experiment/rq4_ablation.yaml --seeds 5
  python scripts/run_experiment.py --config configs/experiment/rq1_detection.yaml --synthetic --epochs 3

Khoá config dùng thêm (tuỳ chọn):
  ablation : [full, no_e_sem, ...]  — mỗi biến thể chạy đủ N seed
  eval_sets: {tên: {split: <giá trị cột split>, where: {cột: giá trị}}}
             mặc định {test: {split: test}}; vd RQ3 thêm {mwf: {split: holdout}},
             RQ2 mỗi level {L3: {split: obf, where: {level: L3}}}.
  data     : {features_dir: data/features_small, max_bytes: 10485760}
  sweep    : {model.taint_predictor.top_k: [4, 8, 16], ...} — tích Descartes; mỗi điểm = một "variant"
             (ablation=full) chạy đủ N seed. Khoá phải tồn tại trong config (bắt lỗi gõ sai).
  select   : {split: val, metric: f1_macro} — chọn điểm sweep có mean tốt nhất -> sweep_best.json.
             Sweep KHÔNG bao giờ ghi numbers.tex (là bước chọn siêu tham số, không phải kết quả).

Đầu ra: experiments/runs/<tên config>/
  <variant>/seed_<s>.json  (metric, lịch sử train, điểm số từng mẫu) ; <variant>/seed_<s>/ (checkpoint)
  summary.json, summary.md, ledger.json (phiên bản/seed/HW/commit — RQF-09)
Chạy lại cùng lệnh sẽ bỏ qua seed đã có JSON và resume seed đang dở.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402

from hipag.eval import _pct_key, tex_macro_name, write_numbers_tex  # noqa: E402
from hipag.model.hipag import ABLATIONS  # noqa: E402
from hipag.train import train_one_seed  # noqa: E402
from hipag.utils.config import load_config  # noqa: E402
from hipag.utils.metrics import aggregate_seeds, format_mean_sd  # noqa: E402

MIN_SEEDS_FOR_PAPER = 5


def set_by_path(cfg: dict, dotted: str, value):
    node = cfg
    *parents, leaf = dotted.split(".")
    for k in parents:
        if not isinstance(node.get(k), dict):
            raise SystemExit(f"sweep: không có khoá '{dotted}' trong config (thiếu '{k}')")
        node = node[k]
    if leaf not in node:
        raise SystemExit(f"sweep: không có khoá '{dotted}' trong config (thiếu '{leaf}')")
    node[leaf] = value


def expand_sweep(sweep: dict) -> list[tuple[str, dict]]:
    """{a.b.top_k: [4, 8], a.b.warmup_epochs: [3]} -> [('top_k4_warmup_epochs3', {...}), ...]."""
    import itertools
    keys = list(sweep)
    points = []
    for combo in itertools.product(*(sweep[k] for k in keys)):
        name = "_".join(f"{k.split('.')[-1]}{v}" for k, v in zip(keys, combo))
        points.append((name, dict(zip(keys, combo))))
    return points


def resolve_seeds(cfg: dict, n: int) -> list[int]:
    base = list(cfg.get("seeds", []))
    extra = [s for s in range(1000) if s not in base]
    return (base + extra)[:n]


def build_data(cfg: dict, synthetic: bool):
    """Trả (train_ds, val_ds, {tên: test_ds})."""
    if synthetic:
        from hipag.data.synthetic import make_synthetic_dataset
        syn = cfg.get("synthetic", {})
        n = int(syn.get("n_train", 128))
        # dữ liệu cố định giữa các seed: chỉ seed MÔ HÌNH thay đổi
        return (make_synthetic_dataset(n, 101), make_synthetic_dataset(n // 2, 202),
                {name: make_synthetic_dataset(n // 2, 303 + k)
                 for k, name in enumerate(cfg.get("eval_sets", {"test": {}}))})
    from hipag.data.dataset import WebshellGraphDataset
    dcfg = cfg.get("data", {})
    feats = ROOT / dcfg.get("features_dir", "data/features_small")
    splits = ROOT / cfg["splits"]
    if not splits.exists():
        raise SystemExit(f"Chưa có {splits} — chạy scripts/dataset/01..05 trước, hoặc thêm --synthetic.")
    mk = lambda split, where=None: WebshellGraphDataset(  # noqa: E731
        str(splits), str(feats), split=split, where=where, max_bytes=int(dcfg.get("max_bytes", 10 * 1024 * 1024)))
    train_ds, val_ds = mk("train"), mk("val")
    tests = {}
    for name, spec in cfg.get("eval_sets", {"test": {"split": "test"}}).items():
        if spec.get("csv"):
            csv_path = ROOT / spec["csv"]
            tests[name] = WebshellGraphDataset(str(csv_path), str(feats), max_bytes=int(dcfg.get("max_bytes", 10 * 1024 * 1024)))
        else:
            tests[name] = mk(spec.get("split", "test"), spec.get("where"))
    for name, ds in [("train", train_ds), ("val", val_ds), *tests.items()]:
        print(f"  {name}: {len(ds)} mẫu (bỏ {len(ds.skipped)})")
        if len(ds) == 0:
            raise SystemExit(f"Tập {name} rỗng — kiểm tra splits.csv / eval_sets.")
    return train_ds, val_ds, tests


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def ledger(cfg, args, seeds, variants) -> dict:
    import torch_geometric
    return {
        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_path": args.config, "config": cfg, "seeds": seeds, "variants": variants,
        "synthetic": args.synthetic, "git_commit": _git_commit(),
        "python": platform.python_version(), "torch": torch.__version__,
        "torch_geometric": torch_geometric.__version__, "cuda": torch.version.cuda,
        "device": args.device,
        "gpu": torch.cuda.get_device_name(0) if args.device.startswith("cuda") and torch.cuda.is_available() else None,
        "platform": platform.platform(),
    }


def report_keys(cfg: dict) -> list[str]:
    rep = cfg.get("report", {})
    keys = list(rep.get("metrics", ["f1_macro", "accuracy", "precision", "recall", "mcc", "pr_auc", "fpr_at_tpr95"]))
    keys += [f"prec_at_base_{_pct_key(p)}" for p in rep.get("base_rate_precision", [0.10, 0.01, 0.001])]
    return keys


def summary_md(summary: dict, keys: list[str], n_seeds: int, synthetic: bool) -> str:
    lines = [f"# Kết quả ({n_seeds} seed, mean ± sd, %; MCC thang [-1,1])"]
    if synthetic:
        lines.append("\n> **DỮ LIỆU GIẢ — smoke test, KHÔNG dùng cho paper.**")
    for set_name in next(iter(summary.values())):
        lines += [f"\n## {set_name}\n", "| variant | " + " | ".join(keys) + " |",
                  "|---|" + "---|" * len(keys)]
        for variant, by_set in summary.items():
            agg = by_set[set_name]
            cells = [format_mean_sd(*agg[k], scale=1.0 if k == "mcc" else 100.0, digits=3 if k == "mcc" else 2)
                     if k in agg else "–" for k in keys]
            lines.append(f"| {variant} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def result_macro_prefix(rq: str, variant: str, set_name: str) -> str:
    """Map the primary RQ1 result to the stable macro names used by main.tex."""
    if rq == "rq1" and variant == "full" and set_name == "test":
        return "HiPaG"
    return tex_macro_name(rq, variant, set_name)


def main(args):
    cfg = load_config(args.config, root=ROOT)
    if args.epochs is not None:
        cfg.setdefault("train", {})["epochs"] = args.epochs
    seeds = resolve_seeds(cfg, args.seeds)
    if cfg.get("sweep"):
        points = dict(expand_sweep(cfg["sweep"]))           # tên điểm -> {đường dẫn: giá trị}
        variants = args.variants or list(points)
        bad = [v for v in variants if v not in points]
        allowed = list(points)
    else:
        points = {}
        variants = args.variants or cfg.get("ablation") or ["full"]
        bad = [v for v in variants if v not in ABLATIONS]
        allowed = ABLATIONS
    if bad:
        raise SystemExit(f"Biến thể không hỗ trợ: {bad}; có: {allowed}")
    tag = Path(args.config).stem + ("_synthetic" if args.synthetic else "")
    out = Path(args.out) if args.out else ROOT / "experiments" / "runs" / tag
    out.mkdir(parents=True, exist_ok=True)
    print(f"[{tag}] seeds={seeds} variants={variants} device={args.device} -> {out}")
    if len(seeds) < MIN_SEEDS_FOR_PAPER:
        print(f"  CẢNH BÁO: {len(seeds)} < {MIN_SEEDS_FOR_PAPER} seed — sẽ KHÔNG ghi numbers.tex.")
    (out / "ledger.json").write_text(json.dumps(ledger(cfg, args, seeds, variants), indent=1, default=str))

    train_ds, val_ds, tests = build_data(cfg, args.synthetic)
    summary: dict = {}
    for variant in variants:
        vcfg = json.loads(json.dumps(cfg))
        if points:
            vcfg["model"]["ablation"] = "full"
            for path, value in points[variant].items():
                set_by_path(vcfg, path, value)
        else:
            vcfg["model"]["ablation"] = variant
        per_set: dict[str, list[dict]] = {"val": [], **{name: [] for name in tests}}
        for seed in seeds:
            f = out / variant / f"seed_{seed}.json"
            if f.exists():
                res = json.loads(f.read_text())
                print(f"  [{variant}] seed {seed}: đã có, bỏ qua")
            else:
                print(f"  [{variant}] seed {seed}: train...")
                res = train_one_seed(vcfg, seed, train_ds, val_ds, tests, args.device,
                                     out_dir=str(out / variant / f"seed_{seed}"),
                                     log=(lambda s: print("    " + s, flush=True)) if args.verbose else (lambda s: None))
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(res, default=float))
            per_set["val"].append(res["val"])
            for name in tests:
                per_set[name].append(res["test"][name])
            print(f"    -> " + ", ".join(f"{n}: F1 {res['test'][n]['f1_macro']:.4f} "
                                         f"PR-AUC {res['test'][n]['pr_auc']:.4f}" for n in tests))
        summary[variant] = {name: aggregate_seeds(rows) for name, rows in per_set.items()}

    keys = report_keys(cfg)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    md = summary_md(summary, keys, len(seeds), args.synthetic)
    (out / "summary.md").write_text(md)
    print("\n" + md)

    if points and cfg.get("select"):
        sel = cfg["select"]
        split, metric = sel.get("split", "val"), sel.get("metric", "f1_macro")
        ranked = sorted(summary, key=lambda v: summary[v][split][metric][0], reverse=True)
        best = ranked[0]
        info = {"select": {"split": split, "metric": metric}, "best": best, "overrides": points[best],
                "mean_sd": summary[best][split][metric], "n_seeds": len(seeds), "synthetic": args.synthetic,
                "ranking": [(v, summary[v][split][metric]) for v in ranked]}
        (out / "sweep_best.json").write_text(json.dumps(info, indent=1, default=float))
        print(f"Điểm tốt nhất theo {split} {metric}: {best} {points[best]} "
              f"= {format_mean_sd(*summary[best][split][metric])} -> sweep_best.json")
    if points:
        print("Sweep -> KHÔNG ghi numbers.tex. Chép giá trị chọn được vào configs/model/hipag_base.yaml.")
        return summary

    tex = args.numbers_tex or cfg.get("report", {}).get("write_numbers_tex")
    if args.no_tex or not tex:
        return summary
    if args.synthetic:
        print("Dữ liệu giả -> KHÔNG ghi numbers.tex.")
        return summary
    if len(seeds) < MIN_SEEDS_FOR_PAPER:
        print(f"<{MIN_SEEDS_FOR_PAPER} seed -> KHÔNG ghi numbers.tex.")
        return summary
    rq = Path(args.config).stem.split("_")[0]           # 'rq1_detection' -> 'rq1' -> \RqOne...
    written = []
    for variant, by_set in summary.items():
        for set_name, agg in by_set.items():
            prefix = result_macro_prefix(rq, variant, set_name)
            aliases = {
                "f1_macro": "Fone",
                "pr_auc": "PRAUC",
                "fpr_at_tpr95": "FPR",
            } if rq == "rq1" and prefix == "HiPaG" else None
            written += write_numbers_tex(agg, str(ROOT / tex), prefix=prefix,
                                         metrics=keys, n_seeds=len(seeds), metric_name_aliases=aliases)
    print(f"Đã ghi {len(written)} macro vào {tex} (vd \\{written[0]})")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--seeds", type=int, default=5, help="số seed (lấy đầu danh sách seeds trong config)")
    ap.add_argument("--variants", nargs="*", help="chỉ chạy các biến thể này (mặc định: config.ablation hoặc full)")
    ap.add_argument("--synthetic", action="store_true", help="smoke test trên dữ liệu GIẢ (không ghi numbers.tex)")
    ap.add_argument("--epochs", type=int, help="ghi đè train.epochs")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", help="thư mục kết quả (mặc định experiments/runs/<config>)")
    ap.add_argument("--numbers-tex", help="ghi đè report.write_numbers_tex")
    ap.add_argument("--no-tex", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true", help="in tiến trình từng epoch")
    main(ap.parse_args())
