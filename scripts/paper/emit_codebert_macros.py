#!/usr/bin/env python3
r"""Emit the \RqOneCodeBert{Test,Holdout}* macros into paper/numbers.tex.

The CodeBERT baseline was run in the code lane and exported a summary JSON; it
does not go through scripts/run_baselines.py, so this paper-side step reads that
JSON and writes the macros with the SAME writer the other RQ1 baselines use
(hipag.eval.write_numbers_tex). That keeps the formatting, the scaling (x100 for
percentages, 3 decimals for MCC) and the trailing provenance comment identical
to the \RqOneBilstm* family, and makes the macros reproducible rather than
hand-typed.

write_numbers_tex is idempotent: macros with the same name are replaced in
place, every other macro in numbers.tex is left untouched.

Run inside hipag_venv:
    python scripts/paper/emit_codebert_macros.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hipag.eval import write_numbers_tex  # noqa: E402

SRC = ROOT / "experiments/runs/rq1_codebert/codebert_rq1_summary.json"
MANIFEST = ROOT / "repro/manifest.json"
NUMBERS = ROOT / "paper/numbers.tex"
SPLITS = ("test", "holdout")

# Values the code lane reported for this run, used only as a read-back check
# that we are pointing at the expected artifact. They are NEVER written to the
# paper: the macros come from the JSON above.
EXPECTED = {
    "test": {"f1_macro": "99.00 +/- 0.51", "mcc": "0.980 +/- 0.010",
             "pr_auc": "99.70 +/- 0.25", "fpr_at_tpr95": "0.17 +/- 0.20",
             "prec_at_base_1pct": "87.03 +/- 14.25",
             "prec_at_base_0p1pct": "57.73 +/- 39.81"},
    "holdout": {"f1_macro": "90.93 +/- 2.32", "mcc": "0.821 +/- 0.046",
                "pr_auc": "83.25 +/- 6.71", "fpr_at_tpr95": "25.45 +/- 41.69",
                "prec_at_base_1pct": "10.41 +/- 5.73",
                "prec_at_base_0p1pct": "1.17 +/- 0.66"},
}


def fmt(metric: str, mean: float, sd: float) -> str:
    """Mirror eval._fmt_value's scaling, for the self-check printout only."""
    scale = 1.0 if metric == "mcc" else 100.0
    d = 3 if metric == "mcc" else 2
    return f"{mean * scale:.{d}f} +/- {sd * scale:.{d}f}"


def main() -> None:
    if not SRC.exists():
        sys.exit(f"STOP: CodeBERT summary not found at {SRC}")
    data = json.loads(SRC.read_text())
    n_seeds = data.get("n_seeds")

    written, failures = [], []
    for split in SPLITS:
        block = data.get(split)
        if not isinstance(block, dict):
            sys.exit(f"STOP: {SRC} has no '{split}' block.")
        agg = {k: (v[0], v[1]) for k, v in block.items()}
        prefix = "RqOneCodeBert" + split.title()
        written += write_numbers_tex(agg, str(NUMBERS), prefix=prefix, n_seeds=n_seeds)

        for metric, want in EXPECTED[split].items():
            got = fmt(metric, *agg[metric])
            flag = "ok " if got == want else "MISMATCH"
            if got != want:
                failures.append(f"{split}.{metric}: got {got}, expected {want}")
            print(f"  [{flag}] {split:8s} {metric:22s} {got}")

    # Share of training files long enough to hit the 8-window cap, i.e. the
    # share whose tail CodeBERT never sees. Read from the repro manifest, which
    # records it as "<hit>/<total>" per split.
    if MANIFEST.exists():
        cap = json.loads(MANIFEST.read_text())["codebert"]["files_hitting_window_cap"]
        hit, total = (int(x) for x in cap["train"].split("/"))
        written += write_numbers_tex(
            {"pct_truncated": (hit / total, float("nan"))}, str(NUMBERS),
            prefix="CodeBertTruncatedTrain",
            metric_name_aliases={"pct_truncated": "Pct"})
        print(f"  [ok ] manifest  train files hitting 8-window cap "
              f"{hit}/{total} = {hit / total * 100:.2f}%")
    else:
        print(f"  [warn] {MANIFEST} absent; \\CodeBertTruncatedTrainPct not emitted")

    print(f"\nsource : {SRC.relative_to(ROOT)} (n_seeds={n_seeds}, "
          f"model={data.get('model')})")
    print(f"wrote  : {len(written)} macros into {NUMBERS.relative_to(ROOT)}")
    for name in written:
        print(f"         \\{name}")
    if failures:
        print("\nSELF-CHECK FAILED:")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("\nself-check: all expected values match the JSON.")


if __name__ == "__main__":
    main()
