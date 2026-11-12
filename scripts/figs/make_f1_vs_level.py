#!/usr/bin/env python3
"""Figure: Macro-F1 by obfuscation level for the three E_sem variants.

Reads the SAME aggregated RQ2 results that eval.py uses to emit the
\\RqTwo{Full,RuleESem,NoESem}L*FOneMacro macros in paper/numbers.tex. Numbers are
NEVER hardcoded and NEVER parsed back from the .tex; this script reads the source
JSON directly. If the source file cannot be found it STOPS with the paths it
tried, rather than inventing numbers.

Output: paper/figs/f1-vs-level.pdf (vector, grayscale, print-safe).
Run inside hipag_venv.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[2]

# Candidate locations for the aggregated RQ2-per-level results (same object that
# feeds the \RqTwo* macros). First existing one with the right structure wins.
CANDIDATES = [
    ROOT / "experiments/runs/rq4_ablation/rq2_per_level_all_metrics.json",
    ROOT / "experiments/runs/rq4_ablation/rq2_per_level_from_rq4_checkpoints.json",
    *sorted(ROOT.glob("experiments/**/rq2*per_level*.json")),
    *sorted(ROOT.glob("results/**/rq2*.json")),
]

# Variant key in JSON -> label in the paper (Table ref{tab:rq2}).
VARIANTS = [("full", "Full"), ("rule_e_sem", "Rule"), ("no_e_sem", "None")]

# Column order matches Table ref{tab:rq2}: clean, then structure-preserving (S),
# then packaging (P).
CLEAN = ["L0"]
GROUP_S = ["L1", "L4"]
GROUP_P = ["L2", "L3", "L5"]
ORDER = CLEAN + GROUP_S + GROUP_P

# Grayscale fills + hatches so the three series stay distinct in B/W print.
STYLE = {
    "Full": dict(facecolor="0.25", hatch=""),
    "Rule": dict(facecolor="0.55", hatch="///"),
    "None": dict(facecolor="0.85", hatch="xxx"),
}


def find_source() -> Path:
    for p in CANDIDATES:
        if p.exists():
            try:
                d = json.loads(p.read_text())
            except Exception:
                continue
            ag = d.get("aggregates")
            if isinstance(ag, dict) and "full" in ag and "L0" in ag.get("full", {}):
                return p
    tried = "\n".join("  " + str(p) for p in CANDIDATES) or "  (no candidates)"
    sys.exit(
        "STOP: could not find an RQ2-per-level results file with the expected\n"
        "aggregates[variant][level]['f1_macro'] = [mean, sd] structure.\n"
        "Paths tried:\n" + tried
    )


def msd(agg: dict, var: str, lvl: str) -> tuple[float, float]:
    """Return (mean%, sd%) for f1_macro; inputs are fractions in [0, 1]."""
    v = agg[var][lvl]["f1_macro"]
    if isinstance(v, dict):
        m, s = v["mean"], v.get("sd", v.get("std", 0.0))
    else:  # [mean, sd, ...]
        m, s = v[0], v[1]
    return m * 100.0, s * 100.0


def main() -> None:
    src = find_source()
    data = json.loads(src.read_text())
    ag = data["aggregates"]
    n_seeds = data.get("n_seeds", "?")

    # Validate every level/variant is present before plotting.
    for _, _ in VARIANTS:
        pass
    for var, _ in VARIANTS:
        for lvl in ORDER:
            if lvl not in ag.get(var, {}):
                sys.exit(f"STOP: {src} is missing aggregates[{var}][{lvl}].")

    x = list(range(len(ORDER)))
    width = 0.26

    plt.rcParams.update({
        "font.size": 9,
        "font.family": "serif",
        "axes.linewidth": 0.6,
    })
    fig, axis = plt.subplots(figsize=(6.2, 3.2))

    # Shaded background bands for the clean / S / P regions.
    bands = [
        (-0.5, len(CLEAN) - 0.5, "0.97", "Clean"),
        (len(CLEAN) - 0.5, len(CLEAN) + len(GROUP_S) - 0.5, "0.90",
         "Structure-preserving (S)"),
        (len(CLEAN) + len(GROUP_S) - 0.5, len(ORDER) - 0.5, "0.80",
         "Packaging (P)"),
    ]
    for lo, hi, shade, label in bands:
        axis.axvspan(lo, hi, color=shade, zorder=0)
        axis.text((lo + hi) / 2.0, 101.5, label, ha="center", va="bottom",
                  fontsize=8, style="italic")

    for i, (var, label) in enumerate(VARIANTS):
        offs = (i - 1) * width
        means = [msd(ag, var, lvl)[0] for lvl in ORDER]
        sds = [msd(ag, var, lvl)[1] for lvl in ORDER]
        axis.bar([xi + offs for xi in x], means, width,
                 yerr=sds, capsize=2.5,
                 edgecolor="black", linewidth=0.6,
                 error_kw=dict(elinewidth=0.6, capthick=0.6, ecolor="black"),
                 label=label, zorder=3, **STYLE[label])

    axis.set_xticks(x)
    axis.set_xticklabels(ORDER)
    axis.set_xlabel("Obfuscation level")
    # matplotlib is not rendering through LaTeX here, so '%' must be literal.
    axis.set_ylabel("Macro-F1 (%)")
    axis.set_ylim(0, 108)
    axis.set_yticks([0, 20, 40, 60, 80, 100])
    axis.set_xlim(-0.5, len(ORDER) - 0.5)
    axis.grid(axis="y", color="0.75", linewidth=0.4, zorder=1)
    axis.set_axisbelow(True)

    handles = [Patch(edgecolor="black", linewidth=0.6, label=lbl, **STYLE[lbl])
               for _, lbl in VARIANTS]
    axis.legend(handles=handles, title="$E_{\\mathrm{sem}}$ variant",
                loc="lower left", fontsize=8, title_fontsize=8,
                framealpha=0.95, ncol=3, columnspacing=1.0)

    out = ROOT / "paper/figs/f1-vs-level.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"source : {src.relative_to(ROOT)}  (n_seeds={n_seeds})")
    print(f"wrote  : {out.relative_to(ROOT)}")
    # Echo the plotted values for cross-check against Table rq2.
    for var, label in VARIANTS:
        row = "  ".join(f"{lvl}={msd(ag, var, lvl)[0]:.2f}+/-{msd(ag, var, lvl)[1]:.2f}"
                        for lvl in ORDER)
        print(f"{label:5s}: {row}")


if __name__ == "__main__":
    main()
