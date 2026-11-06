# Kế hoạch hoàn thiện bài báo HiPaG (webshell PHP) → IJIS

> Dẫn xuất từ `docs/OMNI_RQ_AUDIT_v4_HiPaG_webshell.md`. Verdict audit = **RESCOPE**: cơ chế đáng theo đuổi, nhưng phải **đóng trục Worth + pre-register** *trước khi* đổ công thí nghiệm. Kế hoạch này sắp xếp đúng thứ tự đó và gắn mỗi việc với file trong repo scaffold.

---

## 0. Nguyên tắc chỉ đạo (từ §18 audit)

1. **Đóng Worth trước, code sau.** Trần Worth bị chặn bởi **demand tự-tuyên-bố (W1)** và **novelty-by-composition (W2)**. Hai việc này là đọc–trích–đối-chiếu (effort S–M), phải xong trước khi chạy thí nghiệm — nếu không, số đẹp vẫn mắc band Thấp.
2. **Giữ kỷ luật đặt-claim.** **KHÔNG** thêm claim latency/throughput nào (đây là lý do V9 không kích — giữ sạch FR1). Nếu báo thời gian suy luận, chỉ nói "nằm trong ngân sách", không "nhanh hơn baseline".
3. **Thí nghiệm rẻ-nhất-giết-dự-án chạy sớm.** Ablation **−E_sem** (taint predictor) là phép thử quyết định: nếu E_sem đóng góp <0,5 pp macro-F1 so với chỉ E_cfg/E_dfg ở mọi mức obfuscation → đóng góp lõi không tồn tại, rẽ hướng. Chạy **trước** khi viết bản đầy đủ.
4. **Mọi số của paper sinh từ code + 5 seed + `numbers.tex`.** Không gõ tay số vào bản thảo (chống mâu thuẫn P1-text ↔ P2-table).

---

## 1. Ba tầng (ánh xạ §17 Upgrade Plan)

| Tầng | Mục tiêu | Điểm dự kiến | Effort |
|---|---|---|---|
| **T0 — Pre-code / pre-register** | Đóng mọi điều-kiện-tiền-đăng-ký (demand, novelty-delta, C11, well-pose predictor, metric plan) | Worth 40→46 | ~2–3 tuần-người |
| **T1 — Dữ liệu + pipeline** | Dựng scaffold thành pipeline chạy được; dataset sạch, split cluster-disjoint, ma trận obfuscation, metadata probe PASS | khả thi hoá | ~3–4 tuần-người |
| **T2 — Thực nghiệm** | RQ1–RQ4, 5-seed, ablation 6 thành phần, cross-dataset, base-rate | Worth ~52 · Feas ~64 | ~8–12 tuần-người |
| **T3 — Viết + reproducibility + nộp** | numbers.tex, Threats to Validity, repo public, Data Availability, submit IJIS | Q1-ready | ~3–4 tuần-người |

---

## 2. PHASE T0 — Pre-code (đóng Worth, bắt buộc trước khi chạy)

| # | Việc | Đóng finding | Đầu ra | File liên quan |
|---|---|---|---|---|
| T0.1 | Trích **demand**: ≥1 **E1** (OWASP Testing Guide / CWE-webshell, CWE-94/78 RCE) + ≥1 **E3** (survey webshell) có DOI/URL | RQF-01, RQF-04-demand | Đoạn Introduction + mục Related Work có nguồn | `paper/` (bản thảo .tex sau) |
| T0.2 | **Quét bão hoà prior-art** webshell dựa đồ thị (AST-GCN/CFG-GNN/opcode-graph) trên DBLP/ACM/IEEE/Scopus; lập **bảng delta số** HiPaG vs từng bài | RQF-02 | Bảng so sánh + định vị novelty | `docs/related_work_scan.md` (tạo mới) |
| T0.3 | Viết **C11** tường minh + nhánh kết quả bất lợi | RQF-03 | 1 câu bác-bỏ + cam kết báo cả nhánh thua | `configs/experiment/rq4_ablation.yaml` (đã có mẫu C11) |
| T0.4 | **Well-pose Taint-Dependency Predictor**: seed source/sink, negative sampling, hàm BCE, hiệu chỉnh τ, cửa sổ CFG/DFG | RQF-06 | Spec hình thức + stub đầy đủ | `src/hipag/model/taint_predictor.py`, `src/hipag/graph/taint_seeds.py` |
| T0.5 | Khai **metric plan** 4PV: mỗi metric có đường P4 (tự-tính-lại từ confusion matrix); cam kết PR-AUC/MCC/FPR@TPR95 + base-rate | RQF-07, FR2 | Mục Evaluation Protocol | `src/hipag/eval.py` (đã cài base_rate_precision) |

**Cổng ra T0:** bảy mệnh đề §18(c) của audit đều `CÓ`. Chỉ khi đó mới sang T1.

---

## 3. PHASE T1 — Dữ liệu + pipeline (dựng scaffold thành đồ chạy được)

Thứ tự chạy = thứ tự đánh số `scripts/dataset/`:

| Bước | Script | Việc cốt lõi | Finding |
|---|---|---|---|
| 1 | `01_collect_webshells.py` | Gộp 5 tập, lọc PHP, manifest | — |
| 2 | `02_collect_benign.py` | Lấy mẫu benign **minh bạch** + subset "hard benign" (framework dùng `call_user_func`); báo tỉ lệ lớp | RQF-04 |
| 3 | `03_dedup_cluster.py` | Chuẩn hoá → hash → **near-dup cluster** (minhash) | RQF-05 |
| 4 | `04_build_graphs.py` | PHP → AST/CFG/DFG/call/include → PyG HeteroData; shrink `features_small` | — |
| 5 | `05_make_splits.py` | Split **cluster-disjoint** theo group; MWF tách hẳn (cross-dataset) | RQF-05 |
| 6 | `06_build_obfuscation_matrix.py` | Ma trận obfuscation held-out, **phân tầng level L0–L5** (biến độc lập có thang đo) | RQF-03/K2 |
| 7 | `metadata_probe.py` | **Leakage/shortcut probe** (metadata nông → RandomForest, group-CV). AUC cao bất thường ⇒ sửa dataset trước khi tin model | RQF-04/05 |

**Cổng ra T1 (chuẩn nhóm, giống H-GNN "dataset acceptance"):** metadata probe cho AUC **thấp** (không có shortcut) → mọi độ chính xác của model sau này đến từ cấu trúc code, không từ artefact dữ liệu. Ghi provenance hash vào `experiments/dataset/`.

---

## 4. PHASE T2 — Thực nghiệm (RQ1–RQ4)

Chạy qua `scripts/run_experiment.py --config configs/experiment/<rq>.yaml --seeds 5`:

| RQ | Config | Nội dung | Finding |
|---|---|---|---|
| **RQ4 (chạy TRƯỚC)** | `rq4_ablation.yaml` | **6 ablation** (−token-transformer, −E_sem, −E_dfg, −inter-transformer, −global-feat, pool-mean). **−E_sem là cổng sinh-tử** (§18d) | RQF-10, RQF-03 |
| RQ1 | `rq1_detection.yaml` | HiPaG vs baseline (opcode+CNN, LOGWAT-style, CodeBERT, GCN/GAT, YARA) trên **cùng biểu diễn + cùng tuning** | RQF-08 |
| RQ2 | `rq2_obfuscation.yaml` | Hiệu năng phân tầng theo level obfuscation L0–L5 | RQF-03/K2 |
| RQ3 | `rq3_crossdataset.yaml` | Train 4 tập → test MWF (ngoài phân phối) | K3 |

**Mọi RQ:** 5 seed, `mean ± sd`; báo F1_macro, acc, P, R, **MCC, PR-AUC, FPR@TPR95** + **base-rate precision @ {10%, 1%, 0.1%}** (RQF-07). `eval.py` ghi thẳng macro vào `paper/numbers.tex`.

**Cổng ra T2:** nếu RQ4 cho −E_sem < 0,5 pp ở mọi level → dừng, báo cáo negative result trung thực, cân nhắc rẽ hướng (vẫn là một bài có giá trị: "khi nào taint-edge học được *không* giúp").

---

## 5. PHASE T3 — Viết + reproducibility + nộp

| # | Việc | Finding | File |
|---|---|---|---|
| T3.1 | Viết bản thảo IJIS theo khung Mục 8 phác thảo; `\input{numbers.tex}` cho mọi số | — | `paper/` |
| T3.2 | Mục **Threats to Validity** (4 loại) + **Threat Model** (đã có ở phác thảo Mục 3/9) | RQF-04 (C9 đã PRESENT) | `paper/` |
| T3.3 | **Reproducibility ledger**: seed, version (torch/PyG/CUDA), spec HW, link+hash 5 dataset, repo+README, container; **Data Availability statement** (Springer bắt buộc) | RQF-09 | `README.md`, `experiments/dataset/` |
| T3.4 | Repo public + git hook chặn >5MB/data; manifest commit gzipped | RQF-09 | `tools/git_hooks/pre-commit` |
| T3.5 | Bổ sung ≥3 ref IJIS 2022–2026 (cố định peer-norm) | A-2 | `paper/` |

---

## 6. Bảng truy vết: audit finding → việc → file

| Finding (audit §13) | Sev | Phase | File/đầu ra |
|---|---|---|---|
| RQF-01 Demand tự-tuyên-bố | Major | T0.1 | Introduction + Related Work (E1/E3) |
| RQF-02 Novelty-by-composition | Major | T0.2 | `docs/related_work_scan.md` + bảng delta |
| RQF-03 Thiếu C11 + directional | Major | T0.3, T1-6 | `configs/experiment/rq4_ablation.yaml`, `06_build_obfuscation_matrix.py` |
| RQF-04 Nhãn benign chưa định nghĩa | Major | T0, T1-2 | `02_collect_benign.py`, `configs/dataset/collect.yaml` |
| RQF-05 Dataset nhỏ/cũ/trùng lặp | Major | T1-3,5 | `03_dedup_cluster.py`, `05_make_splits.py` |
| RQF-06 Predictor chưa well-posed | Major | T0.4 | `src/hipag/model/taint_predictor.py` |
| RQF-07 Base-rate/PR-AUC | Major | T0.5, T2 | `src/hipag/eval.py` |
| RQF-08 Baseline chưa cấu hình | Minor | T2 | `rq1_detection.yaml` |
| RQF-09 Reproducibility ledger | Minor | T3.3 | `README.md`, git hook |
| RQF-10 Ablation = K thành phần | Minor | T2 | `rq4_ablation.yaml` |

---

## 7. Mốc kiểm (kill-gates, kiểm nhị phân)

1. **Sau T0:** 7 mệnh đề §18(c) đều `CÓ`? Nếu không → chưa được code.
2. **Sau T1:** metadata probe AUC thấp (dataset không shortcut)? Nếu AUC cao → sửa dataset trước.
3. **Sau RQ4 (−E_sem):** đóng góp E_sem ≥ 0,5 pp ở ≥1 level? Nếu không → negative result, rẽ hướng.
4. **Trước nộp:** `numbers.tex` khớp mọi số trong bản thảo (grep sạch số gõ tay)?

---

## 8. Cấu trúc code (đã scaffold sẵn — xem `README.md`)

```
hipag-webshell/
├── configs/{dataset,model,experiment}/   # YAML, không hardcode
├── scripts/dataset/01..06_*.py           # pipeline đánh số theo thứ tự chạy
├── scripts/{run_experiment,metadata_probe}.py
├── src/hipag/
│   ├── parsing/   php_ast · cfg_dfg · call_include_graph
│   ├── graph/     taint_seeds · node_features · edges · hierarchical_graph
│   ├── model/     token_transformer · taint_predictor · intra_gatv2 · inter_transformer · hipag
│   ├── data/      dataset · collate
│   ├── eval.py    (MCC/PR-AUC/FPR@TPR95 + base-rate precision + numbers.tex)
│   ├── train.py   (5-seed, resume, progress)
│   └── utils/     seed · metrics
├── experiments/{dataset,results}/        # provenance hash, manifest gzipped
├── data/                                 # KHÔNG sync git
├── paper/numbers.tex                     # macro số liệu
└── tools/{php/dump_ast.php, git_hooks/pre-commit}
```

Mọi stub có `TODO(RQF-xx)` trỏ về finding tương ứng. Khởi động:

```bash
python -m venv ~/hipag_venv && source ~/hipag_venv/bin/activate
pip install -r requirements.txt
git init && cp tools/git_hooks/pre-commit .git/hooks/ && chmod +x .git/hooks/pre-commit
```
