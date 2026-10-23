# HiPaG-Webshell

**Hierarchical Program-Graph Transformer for Obfuscation-Resilient PHP Webshell Detection.**

Biểu diễn mỗi file PHP bằng một đồ thị chương trình phân cấp (statement → function → file)
với cạnh đa quan hệ (E_seq / E_skip / E_cfg / E_dfg / E_sem / E_call / E_include), học bằng
Graph-Transformer ba tầng; cạnh ngữ nghĩa source→sink (`E_sem`) là **cạnh học được**
(Learned Taint-Dependency Predictor), không phải luật cứng.

> Repo scaffold này được dựng theo chuẩn nhóm (H-GNN / BFBG-Transformer). Mọi stub có `TODO(RQF-xx)`
> trỏ về finding tương ứng trong `docs/OMNI_RQ_AUDIT_v4_HiPaG_webshell.md`.

## Cấu trúc

```
hipag-webshell/
├── configs/            # YAML cấu hình (dataset / model / experiment) — không hardcode trong code
├── scripts/dataset/    # pipeline dữ liệu, đánh số theo thứ tự chạy
├── scripts/            # run_experiment.py, metadata_probe.py
├── src/hipag/          # thư viện: parsing / graph / model / data / train / eval
├── experiments/        # provenance hash, manifest (commit gzipped), results
├── data/               # KHÔNG sync git — anh để dataset cục bộ ở đây
├── paper/              # numbers.tex (macro số liệu), figs
└── tools/git_hooks/    # pre-commit chặn file >5MB và data/
```

## Quy ước bất di bất dịch (giống H-GNN)

- `data/` **không bao giờ** lên git; số liệu sinh ra ghi provenance hash vào `experiments/dataset/`.
- Split **cluster-disjoint** (near-duplicate không nằm hai phía) — xem `scripts/dataset/05_make_splits.py` (RQF-05).
- Mọi bảng số của paper sinh ≥**5 seed**, báo `mean ± sd`; `eval.py` xuất thẳng macro vào `paper/numbers.tex`.
- Luôn chạy `scripts/metadata_probe.py` trước khi tin kết quả model (RQF-04/05 — chống shortcut/leakage).
- Báo cả **base-rate precision** ở {10%, 1%, 0.1%} + **MCC** + **PR-AUC** + **FPR@TPR95** (RQF-07).

## Môi trường

```bash
python -m venv ~/hipag_venv && source ~/hipag_venv/bin/activate
pip install -r requirements.txt
# Parsing PHP cần PHP + nikic/PHP-Parser (composer) — xem docs/SETUP_PHP.md
```

## Chạy nhanh (sau khi có data/)

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

## Taxonomy seed source/sink (PHP) — xem `src/hipag/graph/taint_seeds.py`

Source: `$_GET $_POST $_REQUEST $_COOKIE $_FILES $_SERVER php://input`
Sink:   `eval assert system exec shell_exec passthru popen proc_open preg_replace(/e) create_function call_user_func call_user_func_array include require`
Decode: `base64_decode gzinflate gzuncompress str_rot13 hex2bin convert_uudecode`
