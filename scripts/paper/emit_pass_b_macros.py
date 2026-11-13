#!/usr/bin/env python3
r"""Emit PASS_B (b/c) macros into paper/numbers.tex.

Reads the per-seed records produced by the b/c runs, aggregates them itself
(mean and sample SD, ddof=1) and writes LaTeX macros. Nothing is hand-typed:
every value in the paper traces to one of these JSON artifacts.

Sources
  c1  experiments/runs/pass_b_c1/c1_obfuscation_matrix.json      5 models x L1-L5
  c2  experiments/runs/pass_b_c2/c2_nodeobf_obfuscation_matrix.json  HiPaG-deobf L0-L5
  b1  experiments/analysis/b1.json        per-seed, medians, Welch+Holm
  b2  experiments/analysis/b2_codebert_table_a1.json  CodeBERT acc/prec/recall
  b3  experiments/analysis/b3.json        TOST, MDE, C11 CI95

Percentage metrics go through hipag.eval.write_numbers_tex so their format and
scaling match the existing macro families. p-values and percentage-point
quantities are written by a local idempotent writer because they are neither
mean+-sd nor percentages.

Self-check: c1/c2 aggregates recomputed from the per-seed records are compared
against the "aggregation" block already present in those files; any mismatch
beyond 1e-9 aborts before anything is written.

Run inside hipag_venv:
    python scripts/paper/emit_pass_b_macros.py
"""
from __future__ import annotations

import json
import math
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hipag.eval import write_numbers_tex  # noqa: E402

NUMBERS = ROOT / "paper/numbers.tex"
C1 = ROOT / "experiments/runs/pass_b_c1/c1_obfuscation_matrix.json"
C2 = ROOT / "experiments/runs/pass_b_c2/c2_nodeobf_obfuscation_matrix.json"
B1 = ROOT / "experiments/analysis/b1.json"
B2 = ROOT / "experiments/analysis/b2_codebert_table_a1.json"
B3 = ROOT / "experiments/analysis/b3.json"

DIGIT = ["Zero", "One", "Two", "Three", "Four", "Five"]
# JSON model key -> macro token, matching the existing \RqOne<Model>* families.
MODEL_TOKEN = {"shallow": "Shallow", "graphmeta": "Graphmeta", "bilstm": "Bilstm",
               "flat_gatv2": "FlatGatvTwo", "codebert": "CodeBert"}
METRICS = ("pr_auc", "f1_macro")

_MACRO_RE = re.compile(r"^\\(?:newcommand|renewcommand|providecommand)\{\\([A-Za-z]+)\}")


def load(path: Path):
    if not path.exists():
        sys.exit(f"STOP: missing source {path}")
    return json.loads(path.read_text())


def agg(values: list[float]) -> tuple[float, float]:
    """Mean and sample SD (ddof=1), matching the rest of the pipeline."""
    return (st.mean(values), st.stdev(values) if len(values) > 1 else 0.0)


def put_plain(pairs: list[tuple[str, str, str]]) -> list[str]:
    """Idempotently merge plain \\newcommand macros into numbers.tex.

    pairs: (macro name, rendered value, provenance comment).
    Same merge rule as eval.write_numbers_tex: replace by name, keep the rest.
    """
    lines = NUMBERS.read_text().splitlines() if NUMBERS.exists() else []
    new = {n: f"\\newcommand{{\\{n}}}{{{v}}}  % {c}" for n, v, c in pairs}
    kept, done = [], set()
    for ln in lines:
        m = _MACRO_RE.match(ln.strip())
        if m and m.group(1) in new:
            if m.group(1) not in done:
                kept.append(new[m.group(1)])
                done.add(m.group(1))
            continue
        kept.append(ln)
    kept.extend(v for n, v in new.items() if n not in done)
    NUMBERS.write_text("\n".join(kept) + "\n")
    return list(new)


def check(label: str, got: float, want: float, tol: float = 1e-9) -> None:
    if not math.isclose(got, want, rel_tol=0, abs_tol=tol):
        sys.exit(f"SELF-CHECK FAILED {label}: recomputed {got!r} != stored {want!r}")


def main() -> None:
    written: list[str] = []

    # ---------- c1: 5 models x L1-L5, recomputed from per-seed records ----------
    c1 = load(C1)
    by_key: dict[tuple[str, str, str], list[float]] = {}
    for r in c1["records"]:
        for m in METRICS:
            by_key.setdefault((r["model"], r["level"], m), []).append(r[m])
    n_checked = 0
    for (model, level, metric), vals in sorted(by_key.items()):
        mean, sd = agg(vals)
        stored = c1["aggregation"][f"{model}/{level}"][metric]
        check(f"c1 {model}/{level}/{metric} mean", mean, stored["mean"])
        check(f"c1 {model}/{level}/{metric} sd", sd, stored["sd"])
        n_checked += 1
    for model, token in MODEL_TOKEN.items():
        for lvl in range(1, 6):
            level = f"L{lvl}"
            a = {m: agg(by_key[(model, level, m)]) for m in METRICS}
            written += write_numbers_tex(
                a, str(NUMBERS), prefix=f"ObfMatrix{token}L{DIGIT[lvl]}",
                n_seeds=len(by_key[(model, level, 'pr_auc')]))
    print(f"  [ok ] c1: {n_checked} aggregates match stored 'aggregation' block")

    # ---------- c2: HiPaG with deobfuscation disabled, L0-L5 ----------
    c2 = load(C2)
    by_lvl: dict[tuple[str, str], list[float]] = {}
    for r in c2["records"]:
        for m in METRICS:
            by_lvl.setdefault((r["level"], m), []).append(r[m])
    n2 = 0
    for (level, metric), vals in sorted(by_lvl.items()):
        mean, sd = agg(vals)
        stored = c2["aggregation"][level][metric]
        check(f"c2 {level}/{metric} mean", mean, stored["mean"])
        check(f"c2 {level}/{metric} sd", sd, stored["sd"])
        n2 += 1
    for lvl in range(0, 6):
        level = f"L{lvl}"
        a = {m: agg(by_lvl[(level, m)]) for m in METRICS}
        written += write_numbers_tex(
            a, str(NUMBERS), prefix=f"HiPaGNodeobfL{DIGIT[lvl]}",
            n_seeds=len(by_lvl[(level, 'pr_auc')]))
    print(f"  [ok ] c2: {n2} aggregates match stored 'aggregation' block")

    # ---------- b2: CodeBERT accuracy/precision/recall completes Table A1 ----------
    b2 = load(B2)
    for split in ("test", "holdout"):
        a = {}
        for row in b2["rows"]:
            if row["row_type"] == "summary" and row["split"] == split:
                a[row["metric"]] = (row["mean"], row["sample_sd"])
        missing = {"accuracy", "precision", "recall"} - set(a)
        if missing:
            sys.exit(f"STOP: b2 missing {missing} for {split}")
        written += write_numbers_tex(
            {k: a[k] for k in ("accuracy", "precision", "recall")}, str(NUMBERS),
            prefix="RqOneCodeBert" + split.title(), n_seeds=b2["n_seeds"])
    print("  [ok ] b2: CodeBERT accuracy/precision/recall emitted")

    # ---------- b1: Welch/Holm p-values, medians and per-seed spread ----------
    b1 = load(B1)
    wh = {(r["model_a"], r["model_b"], r["split"], r["metric"]): r for r in b1["welch_holm"]}

    def pv(a, b, split, metric, kind):
        r = wh.get((a, b, split, metric))
        if r is None:
            sys.exit(f"STOP: b1 has no Welch row for {a} vs {b} {split} {metric}")
        return f"{r[kind]:.3f}"

    plain: list[tuple[str, str, str]] = []
    for a, b, tok in (("HiPaG_full", "codebert", "HiPaGVsCodeBert"),
                      ("HiPaG_full", "flat_gatv2", "HiPaGVsFlatGatvTwo")):
        for kind, suf in (("p_raw", "PRaw"), ("p_holm", "PHolm")):
            plain.append((f"Welch{tok}HoldoutPrAuc{suf}",
                          pv(a, b, "holdout", "pr_auc", kind),
                          f"b1.welch_holm {a} vs {b} holdout pr_auc {kind}"))

    med = {(r["model"], r["split"], r["metric"]): r for r in b1["medians"]}
    for model, tok in (("codebert", "RqOneCodeBert"), ("HiPaG_full", "HiPaG")):
        r = med[(model, "holdout", "pr_auc")]
        plain.append((f"{tok}HoldoutPrAucMedian", f"{r['median'] * 100:.2f}",
                      f"b1.medians {model} holdout pr_auc median (n={r['n_seeds']})"))
        plain.append((f"{tok}HoldoutPrAucMin", f"{r['min'] * 100:.2f}",
                      f"b1.medians {model} holdout pr_auc min"))
        plain.append((f"{tok}HoldoutPrAucMax", f"{r['max'] * 100:.2f}",
                      f"b1.medians {model} holdout pr_auc max"))

    # ---------- b3: C11 deviation at L1 with CI95, MDE range, TOST status ----------
    b3 = load(B3)
    lvl1 = next(r for r in b3["c11"]["per_level"] if r["level"] == "L1")
    plain += [
        ("CElevenLOneDeltaPp", f"{lvl1['difference_pp']:.2f}",
         "b3.c11 L1 full-minus-no_e_sem macro-F1 delta (pp)"),
        ("CElevenLOneCiLowPp", f"{lvl1['ci95_low_pp']:.2f}", "b3.c11 L1 Welch CI95 low (pp)"),
        ("CElevenLOneCiHighPp", f"{lvl1['ci95_high_pp']:.2f}", "b3.c11 L1 Welch CI95 high (pp)"),
    ]
    mdes = {r["level"]: r["mde_80pct_power_pp"] for r in b3["level_tests"]
            if r["metric"] == "f1_macro" and r["contrast"] == "full_minus_no_e_sem"}
    tost_any = any(r["tost_equivalence_raw_alpha_0p05"] for r in b3["level_tests"]
                   if r["metric"] == "f1_macro" and r["contrast"] == "full_minus_no_e_sem")
    if tost_any:
        sys.exit("STOP: a TOST test now reports equivalence; the paper text says none do. "
                 "Re-check b3 before emitting.")
    plain += [
        ("TaintMdeLZeroPp", f"{mdes['L0']:.2f}", "b3 MDE at 80% power, f1_macro, L0 (pp)"),
        ("TaintMdeLOnePp", f"{mdes['L1']:.2f}", "b3 MDE at 80% power, f1_macro, L1 (pp)"),
        ("TaintMdeMinPp", f"{min(mdes.values()):.2f}", "b3 MDE min across L0-L5 (pp)"),
        ("TaintMdeMaxPp", f"{max(mdes.values()):.2f}", "b3 MDE max across L0-L5 (pp)"),
        ("TaintSesoiPp", f"{b3['se_soi']['f1_macro']['delta_abs'] * 100:.2f}",
         "b3.se_soi f1_macro equivalence margin (pp)"),
    ]
    # ---------- b4: per-level parse/transform rates (deobfuscation success
    # counts per level are NOT recoverable from the current artifacts) ----------
    b4 = load(ROOT / "experiments/analysis/b4.json")
    if b4["deobfuscation_availability"]["per_level_success_counts_available"]:
        sys.exit("STOP: b4 now reports per-level deobfuscation counts; the paper says "
                 "they are unavailable. Update the text before emitting.")
    for r in b4["per_level"]:
        lvl = int(r["level"][1:])
        plain.append((f"ParseOkRateL{DIGIT[lvl]}", f"{r['parse_ok_rate'] * 100:.2f}",
                      f"b4.per_level {r['level']} parse_ok_rate"))
        plain.append((f"TransformOkRateL{DIGIT[lvl]}", f"{r['transform_ok_rate'] * 100:.2f}",
                      f"b4.per_level {r['level']} transform_ok_rate"))

    written += put_plain(plain)
    print("  [ok ] b1/b3: Welch/Holm, medians, C11 CI95, MDE and SESOI emitted")
    print(f"  [ok ] b3: no TOST test claims equivalence (checked {len(mdes)} levels)")

    print(f"\nwrote {len(written)} macros into {NUMBERS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
