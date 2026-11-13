# HiPaG-Webshell

** Copyright (©) 2026 Anh Hoang and Hoang Gia Dinh.

**Hierarchical Program-Graph Transformer for Obfuscation-Resilient PHP Webshell Detection.**



HiPaG represents each PHP file as a hierarchical program graph (statement → function → file) with
multi-relational edges (`E_seq` / `E_skip` / `E_cfg` / `E_dfg` / `E_sem` / `E_call` / `E_include`) and learns
it with a three-tier Graph Transformer. The source→sink semantic edges (`E_sem`) are **learned edges**
(a Learned Taint-Dependency Predictor), not hard-coded rules.

> The repository follows the group's project template (H-GNN / BFBG-Transformer). Stubs marked
> `TODO(RQF-xx)` refer to findings of an internal design audit, which is not part of this release.

## Layout

```
hipag-webshell/
├── configs/            # YAML configuration (dataset / model / experiment) — nothing hard-coded in the code
├── scripts/dataset/    # data pipeline, numbered in execution order
├── scripts/            # run_experiment.py, metadata_probe.py
├── src/hipag/          # library: parsing / graph / model / data / train / eval
├── experiments/        # provenance hashes, manifests, results
├── data/               # NOT tracked in git — place your local dataset here
├── paper/              # numbers.tex (result macros), figures — NOT tracked in git
└── tools/git_hooks/    # pre-commit hook that blocks files >5 MB and data/
```

## Conventions

- `data/` is **never** committed; generated artefacts record provenance hashes under `experiments/dataset/`.
- Splits are **cluster-disjoint** (near-duplicates never straddle a split) — see
  `scripts/dataset/05_make_splits.py` (RQF-05).
- Every result table is produced from **≥5 seeds** and reported as `mean ± sd`; `eval.py` writes the
  values directly as macros into `paper/numbers.tex`.
- Always run `scripts/metadata_probe.py` before trusting model results (RQF-04/05 — shortcut / leakage check).
- Report **base-rate precision** at {10%, 1%, 0.1%} together with **MCC**, **PR-AUC** and **FPR@TPR95** (RQF-07).

## Environment

```bash
python -m venv ~/hipag_venv && source ~/hipag_venv/bin/activate
pip install -r requirements.txt
# Parsing PHP requires PHP + nikic/PHP-Parser (Composer) — see docs/SETUP_PHP.md
```

## Quick start (once data/ is in place)

```bash
python scripts/dataset/01_collect_webshells.py  --config configs/dataset/collect.yaml
python scripts/dataset/02_collect_benign.py     --config configs/dataset/collect.yaml
python scripts/dataset/03_dedup_cluster.py      --config configs/dataset/dedup.yaml
python scripts/dataset/04_build_graphs.py       --config configs/dataset/build_graphs.yaml
python scripts/dataset/05_make_splits.py        --config configs/dataset/split.yaml
python scripts/dataset/06_build_obfuscation_matrix.py --config configs/dataset/obfuscation.yaml
python scripts/metadata_probe.py                --config configs/experiment/rq1_detection.yaml
python scripts/run_experiment.py                --config configs/experiment/rq1_detection.yaml --seeds 5
```

## PHP source/sink seed taxonomy — see `src/hipag/graph/taint_seeds.py`

Abridged; `taint_seeds.py` holds the authoritative, current lists.

Source: `$_GET $_POST $_REQUEST $_COOKIE $_FILES $_SERVER php://input`
Sink:   `eval assert system exec shell_exec passthru popen proc_open preg_replace(/e) create_function call_user_func call_user_func_array include require`
Decode: `base64_decode gzinflate gzuncompress str_rot13 hex2bin convert_uudecode`
