# Related-work scan — webshell detection dựa đồ thị (T0.2, đóng RQF-02)

> Quét ngày 2026-11-06 (DBLP / ScienceDirect / arXiv / ResearchGate). Mục tiêu: xác lập **delta** của
> HiPaG so với prior-art, và chứng minh novelty **không** chỉ là "ghép T-CFBG + LOGWAT".
> Số đối thủ (nếu trích được công khai) chỉ là tham khảo; delta thật lấy từ RQ1 — ta tái lập đối thủ trên split của ta.

## Nearest-neighbour (các bộ phát hiện webshell dựa biểu diễn cấu trúc)

| Công trình | Venue / năm / DOI | Biểu diễn đồ thị | Mô hình | Node features | Dataset | Phán quyết vs HiPaG |
|---|---|---|---|---|---|---|
| **GlareShell** — Feng et al. | Computer Networks 245:110406 (2024), doi:10.1016/j.comnet.2024.110406 | **ICFG phẳng** (interprocedural CFG), có prune | GNN (không nêu rõ loại) | word-embedding câu lệnh **+ risk level gán tay** | ~3K webshell / 10K benign PHP | **OVERLAPPING — nearest neighbour.** Khác biệt cốt lõi: GlareShell dùng *risk weight gán tay* trên ICFG *phẳng*; HiPaG thay bằng *taint source→sink **học được*** + *phân cấp 3 tầng* + *Token-Transformer* |
| **SAWD** — Structural-Aware Webshell Detection | CFG-based (RG 373615619) | CFG đơn | (structural-aware) | — | PHP | **DISTINCT** — CFG một mức, không taint học được, không phân cấp |
| **AST-DF** — Abstract Syntax Tree + Deep Forest | Electronics (MDPI), URL path /13/8/1482 | AST | Deep Forest | AST node | PHP | **DISTINCT** — AST tĩnh + forest, không CFG/DFG, không GNN |
| AST simplification + EDRN | Computers & Security (2024), pii S0167404824003547 | AST đơn giản hoá | Explicit Duration RNN | token AST | PHP | **DISTINCT** — tuần tự trên AST, không đồ thị đa quan hệ |
| Long PHP webshell — sliding-window attention | arXiv:2502.19257 (2025) | chuỗi token | attention cửa sổ trượt | token | PHP dài | **DISTINCT** — lexical/sequence, đúng loại baseline HiPaG vượt |
| CNN-Webshell | (RG 323819078) | chuỗi opcode | CNN | opcode | PHP | **DISTINCT** — baseline lexical kinh điển |
| Incremental learning for webshell | Springer (2025), doi:10.1007/s44443-025-00235-8 | — | incremental | — | webshell | **DISTINCT** — trục incremental learning, khác mục tiêu |
| Flexible dataset reduction | Computers & Security (2025), pii S111086652500163X | — | DL + giảm dữ liệu | — | webshell | **DISTINCT** — trục hiệu quả dữ liệu |
| JShellDetector | pii S1546221823004113 | program analysis | — | — | **Java** fileless | **DISTINCT** — khác ngôn ngữ (Java), fileless |

## Định vị novelty của HiPaG (neo được, không phải composition suông)

Nearest neighbour là **GlareShell**. So trực tiếp, HiPaG mới ở **ba điểm tách bạch**:

1. **Taint source→sink HỌC ĐƯỢC thay cho risk-weight GÁN TAY.** GlareShell gán *risk level* thủ công cho câu
   lệnh; HiPaG học quan hệ source→sink bằng link-prediction yếu-giám-sát (Learned Taint-Dependency Predictor).
   Đây đúng là bài học LOGWAT — thay luật cứng bằng cạnh học được — lần đầu áp cho webshell.
2. **Phân cấp statement→function→file** thay cho ICFG **phẳng** một mức: bắt được webshell **đa-file**
   (include/require) mà ICFG phẳng của GlareShell không mô hình hoá.
3. **Token-Sequence Transformer** cho đặc trưng nút theo ngữ cảnh, thay word-embedding tĩnh.

⇒ **Không công trình nào SUBSUMED** (mọi cái DISTINCT trừ GlareShell OVERLAPPING). W2 có chỗ đứng để lên 3
khi bảng delta RQ1 (tái lập GlareShell làm baseline trực tiếp trên split của ta) cho số HiPaG vượt.

## Hệ quả cho repo / thí nghiệm
- **Thêm GlareShell vào baseline** (RQ1) — đối thủ graph trực tiếp nhất; nếu không tái lập được, giải trình rõ.
- **Ablation then chốt:** HiPaG(full) vs HiPaG(−E_sem thay bằng risk-weight-gán-tay kiểu GlareShell) — cô lập đúng
  đóng góp "học được vs gán tay".

## Tuyên bố bão hoà
- [x] Quét ScienceDirect/arXiv/Springer/MDPI/DBLP — nhánh webshell-graph đã gặp GlareShell + SAWD + AST-DF là
  cụm gần nhất; chưa thấy công trình nào SUBSUMED HiPaG. **Khuyến nghị quét bổ sung IEEE Xplore + ACM DL** để
  chốt bão hoà hoàn toàn trước khi nộp.
- W2 lên 3 khi **bảng delta RQ1** (tái lập đối thủ trên split của ta) cho thấy HiPaG hơn — không phụ thuộc số tác giả tự công bố.

---

## Bước 7 — Số đối thủ công bố (chỉ tham khảo; mốc thật = tái lập ở RQ1)

> **Nguyên tắc:** mình làm từ đầu — mốc so sánh của HiPaG là **tái lập đối thủ trên chính split cluster-disjoint
> của ta** (RQ1), không phải số tác giả tự công bố. Số tự công bố ở dưới (nếu có) chỉ để biết prior-art đứng đâu;
> mỗi số là trên **dataset + split RIÊNG của họ**, tỉ lệ lớp khác → **không so trực tiếp**. Các số này KHÔNG vào
> `numbers.tex` (file đó chỉ chứa số thực nghiệm của ta, tự sinh).

| Công trình | Dataset (của họ) | Acc | Precision | Recall | F1 | Nguồn |
|---|---|---|---|---|---|---|
| **AST-DF** (Electronics 13(8):1482, 2024) | 1,907 webshell / 11,004 benign PHP | 99.61% | 99.12% | 99.34% | 99.24% | MDPI open-access, Table 7 (hàng "Deep Forest") |
| **GlareShell** (Feng 2024) | ~3K webshell / 10K benign PHP | — | — | — | — | Abstract + bài trích dẫn công khai không nêu số; **không cần trích** — tái lập ở RQ1 là mốc thật |

**Baseline phụ trong bài AST-DF (cùng dataset của họ, Table 7–9)** — tham khảo khi dựng bảng baseline RQ1:
- Cổ điển: SVM F1 93.14 · RandomForest 98.22 · XGBoost 98.43 · MLP 96.05 (Acc/Pre/Recall xem Table 7).
- Công cụ sẵn có: D-Shield F1 94.38 · Webshellpub 75.20 · CloudWalker 74.73 (Table 9) — tool luật-cứng rớt mạnh ở recall.
- *Mâu thuẫn trong bài AST-DF:* text nói Ref [37] đạt 99.25% acc nhưng Table 8 ghi 98.91% acc / 99.25% precision — nếu trích ghi theo bảng.

**Kết luận Bước 7:** không có "nợ" phải đi xin số ở đâu. GlareShell + các baseline đều **tái lập trong RQ1** trên split
của ta; nếu đối thủ nào không tái lập được thì giải trình rõ. Số AST-DF công khai giữ làm điểm neo tham khảo.

---

## Bổ sung 06/11 — nhánh obfuscation-evasion (củng cố gap)

| Công trình | Định danh | Góc độ | Phán quyết vs HiPaG |
|---|---|---|---|
| CWSOGG | ResearchGate 363084032 | Sinh webshell obfuscated (GA+GAN) né phát hiện | DISTINCT — phía tấn công/sinh; chứng minh gap của HiPaG là thật |
| MMFDetect | Electronics 14(3):416 (2025), doi:10.3390/electronics14030416 | Multimodal feature fusion chống evasion | OVERLAPPING-nhẹ — cùng mục tiêu kháng evasion, khác biểu diễn (không đồ thị phân cấp/taint học được) |
| MITRE ATT&CK T1505.003 | attack.mitre.org/techniques/T1505/003 | Standards anchor | — (neo demand, không phải baseline) |
