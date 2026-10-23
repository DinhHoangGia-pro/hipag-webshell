# OMNI_RQ_AUDIT v4.0 — Báo cáo thẩm định
## Đề cương: "HiPaG — Hierarchical Program-Graph Transformer for Obfuscation-Resilient PHP Webshell Detection" (phác thảo, định hướng IJIS/Springer 10207)

---

# §0. AUDIT HEADER

| Trường | Giá trị |
|---|---|
| Protocol ID | OMNI_RQ_AUDIT_v4.0 |
| Ngày chạy | 2026-10-23 |
| Đối tượng | **Phác thảo HiPaG** — Dinh Hoang; đồ thị chương trình phân cấp (statement→function→file) + Graph-Transformer cho phát hiện webshell PHP |
| MODE | `EXTRACT_AND_AUDIT` |
| DOMAIN | Phát hiện webshell / ML an ninh tầng ứng dụng (phân tích mã nguồn tĩnh) |
| OUTPUT_LANGUAGE | Tiếng Việt |
| STRICTNESS | `Q1-hostile` |
| PASS | `FULL` |
| **VENUE** (tham số phiên) | **International Journal of Information Security** (Springer, 10207). Một venue chốt ⇒ peer-norm T15/F6/W5 **KHÔNG** `PROVISIONAL` ở trục venue-determination |
| Evidence Completeness | **6/14** (1 PRESENT · 8 PARTIAL · 5 MISSING) |
| Tin cậy tổng thể | **TRUNG BÌNH** — đối tượng là **đề cương**, không phải manuscript hoàn chỉnh; nhiều slot là *kế hoạch pre-commit* chứ chưa *thực thi*, nên finding mang tính **tiền-đăng-ký** (shift-left) chứ không phải lỗi số liệu đã xảy ra |
| **Manuscript version** | Phác thảo doc "Phác thảo bài báo Q1 — webshell PHP/Python…", bản sau khi chốt scope PHP (2026-10-23). Không có changelog nội bộ ⇒ mọi finding neo vào text hiện tại của phác thảo |

**Lưu ý đọc báo cáo.** Khác với một manuscript đã viết xong (ví dụ audit LOGWAT), đối tượng ở đây là **đề cương chưa chạy thí nghiệm**. Vì vậy phần lớn gate forensic được đánh giá ở dạng *"kế hoạch có pre-commit đủ để sau này sống sót autopsy không"* — đúng mục đích shift-left của v4.0. Điểm số phản ánh **đề cương như đang phát biểu**, không phải một hệ đã có kết quả.

---

# §1. VERDICT TỔNG HỢP

> **Worth = 40/100 [Thấp]** · **Feasibility = 47/100 [Thấp, sát ngưỡng]** · Ô ma trận §18: **Feas <50 × Worth <50 → TỪ BỎ *cách-đặt-vấn-đề-hiện-tại*** (không có veto nào kích; quyết định rơi vào vùng FRAGILE nên §18 chốt bằng finding, không bằng con số) · Q1 Readiness: **Q1-REACHABLE** · Forensic-Readiness: **GAPS-PLANNABLE**.
>
> Kết luận khả thi: **cơ chế lõi (bất biến cấu trúc source→sink sống sót obfuscation, học bằng đồ thị phân cấp) là hợp lý và đáng theo đuổi**; nhưng đề cương **như đang phát biểu** chưa đủ để nhắm IJIS vì hai lý do thuộc trục Worth — **demand tự-tuyên-bố** và **novelty-by-composition chưa xác lập delta** — cộng với việc RQ/tiêu-chí-bác-bỏ/ablation chưa được pre-register tường minh.
>
> **Điểm khác biệt quyết định so với một bài yếu điển hình (anti-pattern "số đẹp"):** đề cương **KHÔNG** có claim latency/throughput nào ⇒ **FR1 sạch, V9 không kích** (tránh được nguyên cả lớp lỗi `PHYSICS_VIOLATION`); và đề cương **đã pre-commit** ablation (RQ4), cross-dataset held-out (MWF), metric FPR-centric, ≥5 seed. Đây là lý do Forensic-Readiness = `GAPS-PLANNABLE` chứ không `STRUCTURAL-RISK`.
>
> **Ba blocker hàng đầu**
> 1. **RQF-01 (Major, W1)** — Demand tự-tuyên-bố. Mốc "21/10/2026" chưa có nguồn; chưa trích bất kỳ E1 (điều khoản OWASP ASVS/Testing Guide về webshell/RCE) hay E2 (CVE/sự cố/telemetry) nào. W1 bị **trần E3** chặn ở mức tốt nhất là 3, hiện thực tế ≈ 2.
> 2. **RQF-02 (Major, W2)** — Novelty-by-composition (`AP-07`). HiPaG = T-CFBG (phân cấp) ⊕ LOGWAT (đa quan hệ) chuyển miền sang PHP. Delta so với **các bộ phát hiện webshell dựa đồ thị AST/opcode đã công bố** chưa được xác lập bằng số; chưa có quét bão hoà.
> 3. **RQF-03 (Major, F1/F2)** — Chưa có **tiêu chí bác bỏ (C11)** tường minh và khung đang **chỉ-thuận** (directional). Chưa phát biểu "coi là KHÔNG nếu −E_sem cải thiện <0,5 pp macro-F1 ở mọi mức obfuscation".
>
> **Độ phủ bằng chứng.** Chỉ **2 điểm ≥3** (W5 Fit, F4 Resource) có neo so sánh; phần còn lại là điểm ≤2 không cần neo. **Kích cờ `FRAGILE-BAND`** ở trục Feasibility: 47/100 cách ngưỡng 50 chỉ 3 điểm, nhiễu ±20% trọng số có thể lật band Feas giữa Thấp↔Trung bình. Vì vậy §18 **không** quyết bằng con số mà bằng finding (thoả V-C6/V-C7): không veto nào kích, cơ chế hợp lý ⇒ thực chất là **RESCOPE-nghiêng**, nhưng **trần Worth** là ràng buộc ràng buộc nhất.

---

# §2. EVIDENCE PROFILE — bảng trích C1–C14

| Slot | §nguồn (phác thảo) | Trích/ghi chú | Trạng thái |
|---|---|---|---|
| **C1** Tiêu đề + venue + aims&scope | Mục 1 | Ba phương án tiêu đề có; venue = IJIS (cấp ở SESSION). Aims&scope nguyên văn của bài chưa viết | **PARTIAL** |
| **C2** Problem statement ≤150 từ, không nhắc giải pháp | Mục 1 (pitch) | Vấn đề nêu rõ: lexical/opcode+CNN sụp đổ trước obfuscation; nhưng đoạn đã **trộn tên giải pháp** (đồ thị phân cấp, Graph-Transformer) | **PARTIAL** |
| **C3** Research questions nguyên văn, đánh số | Mục 7 | **CÓ** RQ1–RQ5 đánh số (hiệu năng, kháng obfuscation, cross-dataset, ablation, chi phí). Phát biểu còn ở dạng câu hỏi khung, chưa thao-tác-hoá hoàn toàn | **PARTIAL→PRESENT** |
| **C4** contribution→method→metric→**baseline**→artifact | Mục 2, 5, 7 | 4 đóng góp rõ; method rõ; metric rõ (Acc/P/R/F1/AUC/FPR); baseline **có tên** (opcode+CNN, LOGWAT-style, CodeBERT, GCN/GAT, YARA) nhưng **chưa cấu hình/chưa chạy**; artifact: nêu ý định (script + hash registry) chưa có ledger | **PARTIAL** |
| **C5** 5–10 công trình gần nhất + DOI + delta | Mục 10 | Nền nhóm (T-CFBG, LOGWAT) + hướng cần bổ sung; **0 DOI**, **chưa quét bão hoà prior-art webshell-graph** | **MISSING→PARTIAL** |
| **C6** Threat model (adversary, trust boundary, goal, assumption) | Mục 3 | **CÓ** mô hình kẻ tấn công: năng lực (obfuscation gi ng ngữ nghĩa), ranh giới (tĩnh, mức file), **loại trừ tường minh** adversary gradient-based. Security goal + assumption-set còn mỏng | **PARTIAL** |
| **C7** Ràng buộc (testbed/thời gian/nhân lực/dữ liệu/ethics) | Mục 6 | Dữ liệu nêu; thời gian/nhân lực/ethics chưa → **advisory NON-BLOCKING** (AF-10) | **PARTIAL** |
| **C8** Beneficiary map | Mục 1, 8 | "điều tra viên", "CI/CD / WAF log scanner". Chưa có tác nhân/quyết định cụ thể | **PARTIAL** |
| **C9** Điểm yếu tác giả tự nhận biết | Mục 9 | **CÓ** mục hạn chế + threats to validity (parse khi obfuscation nặng, nhãn nhiễu, benign mất cân bằng, giới hạn ngôn ngữ). Điểm cộng rõ rệt | **PRESENT** |
| **C10** Demand evidence E1–E5 + URL/DOI | Mục 1, 10 | Chưa trích điều khoản/CVE/survey nào có DOI. Mốc 21/10/2026 chưa nguồn. Thực chất hiện ở **E5** (phán đoán tác giả) | **MISSING** |
| **C11** Tiêu chí bác bỏ tiền đăng ký | — | Chưa viết "coi là KHÔNG nếu…" → slot *đề-xuất*, nhưng là đầu vào của **V10** | **MISSING** |
| **C12** Sổ nguồn lực + % ngân sách | — | Không có → advisory NON-BLOCKING; V6 KHÔNG áp | **MISSING** |
| **C13** Động lực thời điểm (điều gì **mới thay đổi**) | Mục 1 | Mốc 21/10/2026 được viện như động lực nhưng **chưa nguồn, chưa nêu thay đổi cụ thể** (làn sóng tấn công/quy định mới) | **MISSING→PARTIAL** |
| **C14** Assurance Claim Register | Mục 7 (ngầm) | Claim "tốt hơn baseline" + "kháng obfuscation" + "tổng quát cross-dataset"; phương pháp kiểm **có khai** (ablation, held-out, ≥5 seed) nhưng chưa thành register | **PARTIAL** |

**Hồ sơ tier nhu cầu (C10):** E1 = 0 · E2 = 0 · E3 = 0 (chưa trích survey có DOI) · E4 = 0 · E5 = toàn bộ.
**Trần W1 (P1.3): hiện chỉ E5 ⇒ trần `W1 ≤ 1` theo luật cứng.** *Nới tạm lên trần 3 nếu đề cương bổ sung ≥1 survey webshell (E3) — việc effort S — nên §8 chấm W1=2 với ghi chú "trần sẽ mở khi trích E3", chứ không chốt 1.*

**Nhận định.** Tầm quan trọng của **lĩnh vực** webshell là có thật và dễ chứng thực bằng E3 (nhiều survey/SoK về webshell detection) — nhưng đề cương **chưa trích**. Tầm quan trọng của **khoảng trống cụ thể** ("đồ thị phân cấp source→sink cho webshell") hiện là **tự-tuyên-bố** (technique-driven). Đây là chỗ sửa rẻ nhất và tác động lớn nhất lên Worth.

---

# §3. CLASSIFICATION & WEIGHT PROFILE

| Trục | Kết quả |
|---|---|
| **RQ (trích)** | RQ1–RQ5 (Mục 7) — **PRESENT nhưng chưa thao-tác-hoá** (chưa gắn ngưỡng/biến độc lập có thang đo) |
| **Wieringa** | **Design problem** trội (xây artifact HiPaG) + knowledge question nhúng (E_sem học được có tăng F1 dưới obfuscation không?) |
| **Shaw** | Loại RQ: *method/means of development*. Validation tuyên bố: *evaluation (benchmark + ablation + cross-dataset)* — tham vọng đúng hướng, nhưng **chưa thực thi** |
| **Sedlmair** | **Technique-driven** (khoảng trống định nghĩa bằng vắng-mặt-kỹ-thuật ở Mục 1–2) ⇒ **T1, T11 áp nghiêm hơn** |
| **PICOC** | P: file PHP (5 tập webshell + benign CMS) · I: đồ thị phân cấp + Token-Transformer + GATv2 + Inter-proc Transformer + taint predictor · C: opcode+CNN, LOGWAT-style, CodeBERT, GCN/GAT, YARA · O: Acc/P/R/F1/AUC/**FPR** · C(ontext): 1 GPU, kháng obfuscation held-out |
| **Archetype** | **Lai P2 × P3** (thiết kế kiến trúc × benchmark) |
| **Anti-pattern phát hiện** | `AP-07` (novelty-by-composition) · `AP-20`-risk (directional, do thiếu C11) · `AP-09`-nhẹ (mốc 21/10 chưa nguồn) · **KHÔNG** `AP-21` (không claim hiệu năng) · **KHÔNG** `AP-17` (claim trung tâm *có* khai phương pháp kiểm) |

### Hồ sơ trọng số đã KHOÁ (P1.2) và lý do

Lai **P2 × P3**: có kiến trúc đề xuất (nghiêng P2) nhưng toàn bộ claim sẽ là số benchmark (nghiêng P3). Lấy **trung bình hai hồ sơ** (khai minh bạch; cấm chọn hồ sơ lợi nhất).

**WORTH (khoá):** W1 = 32,5 · W2 = 22,5 · W3 = 25 · W4 = 10 · W5 = 10 — tổng 100 ✔
**FEASIBILITY (khoá):** F1 = 19 · F2 = 21 · F3 = 20 · F4 = 15 · F5 = 7 · F6 = 7,5 · F7 = 4,5 · F8 = 6 — tổng 100 ✔

---

# §4. ASSURANCE REQUIREMENT DETERMINATION

| # | Claim (dự kiến) | Loại | Tier yêu cầu | Tier dự kiến | Phán quyết |
|---|---|---|---|---|---|
| **K1** | "HiPaG vượt baseline lexical và đồ-thị-phẳng" | Tốt hơn baseline | A0 + kỷ luật thực nghiệm (split công bố, variance, ablation) | **Đã khai** ablation + ≥5 seed + cross-dataset | **ĐỦ-trên-kế-hoạch** (chưa thực thi) |
| **K2** | "Kháng obfuscation tốt hơn baseline từ vựng" | Tốt hơn, có điều kiện | A0 + thí nghiệm **phân tầng theo mức obfuscation** | Khai "ma trận obfuscation held-out" nhưng **chưa nêu thang đo mức obfuscation** (0/5/10/20 token nhiễu) | **PARTIAL** — cần thao-tác-hoá biến obfuscation |
| **K3** | "Tổng quát cross-dataset (MWF ngoài phân phối)" | Khái quát hoá | A0 + held-out cross-dataset | Khai MWF never-trained-on | **ĐỦ-trên-kế-hoạch** |
| **K4** | "E_sem học được bắt source→sink gián tiếp mà luật cứng bỏ sót" | Cơ chế | A0 + ablation tách E_sem + đo độ phủ | Khai ablation (RQ4) nhưng **chưa khai phép đo độ phủ** của predictor | **PARTIAL** |
| **K5** | (KHÔNG có claim latency/throughput) | — | — | — | **N/A — tránh được V9** ✔ |

**Tier kỳ vọng venue (từ C5).** IJIS (Springer 10207) thường đăng ML cho phát hiện xâm nhập/malware/web attack ở tier **A0 + kỷ luật thực nghiệm mạnh** (ablation, cross-dataset, artifact). **Chưa trích đủ ≥3 bài IJIS 2022–2026** ⇒ trục phân bố peer-norm `INSUFFICIENT EVIDENCE` (đưa vào §20), nhưng VENUE đã chốt nên T15/F6/W5 vẫn chấm được, tin cậy T15 **THẤP**.

**Mắt xích chưa cơ giới hoá (P2.5).**
1. **Learned Taint-Dependency Predictor** — chưa khai: tập seed taint rule chính xác, cách sinh negative, hàm huấn luyện, ngưỡng τ hiệu chỉnh ở đâu, cửa sổ CFG/DFG cho cặp ứng viên.
2. **Ánh xạ "benign"** — chưa khai thủ tục lấy mẫu benign từ CMS, tỉ lệ lớp, và cách chống việc code CMS hợp lệ dùng `call_user_func` bị gán nhãn sai.
3. **Độ phủ bảng seed** — chưa có phép đo % webshell trong test kích hoạt ≥1 luật seed (phép thử trực tiếp cho claim "bắt cái luật cứng bỏ sót").

---

# §5. RED TEAM ASSAULT

| ATK | Trục | Luận điểm | Bằng chứng (phác thảo) | Severity đề xuất |
|---|---|---|---|---|
| **ATK-01** | W2 · `AP-07` | Novelty-by-composition: HiPaG = T-CFBG ⊕ LOGWAT đổi miền; mỗi mảnh đã công bố | Mục 1 "sự hợp nhất có chủ đích giữa hai công trình đã có"; Mục 2 bảng định vị | **Major** |
| **ATK-02** | W1 · `AP-09`/E5 | Demand tự-tuyên-bố; mốc 21/10/2026 chưa nguồn; 0 điều khoản/CVE | Mục 1; C10 = 0 E1/E2/E3 | **Major** |
| **ATK-03** | F1 · `AP-20` | Khung chỉ-thuận: chưa có C11, chưa có nhánh "E_sem không giúp" | Mục 7 (RQ không kèm tiêu chí bác bỏ) | **Major** |
| **ATK-04** | W2/F3 · T3 | Phương án chuẩn hoá đơn giản chưa bị loại: Bi-LSTM/CodeBERT trên opcode + đặc trưng cặp source-sink regex có thể đạt tương đương | Mục 7 có CodeBERT trong baseline nhưng **chưa cam kết** biến thể "token + cặp source-sink" | **Major** |
| **ATK-05** | F2-construct | Nhãn "benign" chưa định nghĩa; FPR phụ thuộc cấu tạo tập benign | Mục 6 "benign lấy từ mã PHP sạch quy mô lớn" — chưa thủ tục | **Major** |
| **ATK-06** | F2-external | 5 tập nhỏ (~7–8k), cũ (2015–2022), trùng lặp; cross-dataset chỉ 1 held-out (MWF) | Mục 6 bảng dataset | **Major** |
| **ATK-07** | F6/T22 · `AP-18`-risk | "Learned Taint-Dependency Predictor" chưa well-posed: seed, negative sampling, τ, hàm Validity chưa định nghĩa | Mục 3, 5 | **Major** |
| **ATK-08** | T11 | Mỗi thành phần (3 tầng, Token-Transformer, taint predictor, inter-proc) — bỏ đi thì RQ còn trả lời được? chưa chứng minh "cần" | Mục 4 | **Major (thành phần)** |
| **ATK-09** | W3/base-rate | Webshell cực hiếm trong prod; chưa cam kết báo PR-AUC/MCC + FPR ở base-rate thực | Mục 7 có nêu FPR nhưng chưa nêu base-rate/PR-AUC | **Major** |
| **ATK-10** | F8 | Chưa có reproducibility ledger cụ thể (seed/version/hash/container) dù nêu ý định | Mục 6 | **Minor→Major** |

### T5 — Ba câu desk-reject tàn nhẫn nhất (dự phóng cho bản viết xong)

1. *"The novelty is a cross-domain recombination of the authors' two prior frameworks; the manuscript must establish a numeric delta against published graph-based webshell detectors, which it does not cite."*
2. *"No falsification criterion is stated and no experiment stratifies performance by obfuscation level, so the central 'obfuscation-resilient' claim is not operationalised."*
3. *"The datasets are small, dated and duplication-heavy; without source-level dedup and a reported clean subset, the headline numbers are not trustworthy."*

### Ưu điểm Red **không đánh được** (P4.2 — nêu TRƯỚC phản hồi Blue)

- **RQS-A.** Cơ chế lõi đúng và cụ thể: lexical/opcode-sequence vỡ khi obfuscation phá thứ tự token, trong khi **đường source→sink tồn tại bất biến**; đây là chẩn đoán chế độ lỗi chính xác và **khả nghiệm về nguyên tắc**. Con trỏ: Mục 1, 5.
- **RQS-B.** Đề cương **không đưa claim latency** nào ⇒ tránh được nguyên lớp lỗi `PHYSICS_VIOLATION` mà các bài "real-time WAF" thường chết (đối chiếu audit LOGWAT: V9 kích vì 3,7 ms). Đây là kỷ luật đặt-claim tốt.

---

# §6. BLUE TEAM DEFENCE

| ATK | Phản hồi | Lập luận (chỉ dùng C1–C14) |
|---|---|---|
| ATK-01 | **MITIGATE** | Mục 2 tuyên bố đóng góp lõi là **Learned Taint-Dependency Predictor** (thay luật cứng bằng link-prediction) + **phân cấp 3 tầng cho script** — không có tiền lệ webshell nào có cả hai. Nhưng Blue **không** trích được bài webshell-graph nào để định lượng delta. |
| ATK-02 | **CONCEDE** ✅ | C10 = 0 E1/E2/E3 có DOI. Mốc 21/10/2026 chưa nguồn. Blue nhượng bộ toàn phần: demand hiện tự-tuyên-bố. |
| ATK-03 | **CONCEDE** ✅ | Không có câu C11 nào trong phác thảo. Blue nhượng bộ toàn phần. |
| ATK-04 | **MITIGATE** | Mục 7 có CodeBERT + GCN/GAT trong baseline; Blue đề nghị đọc "baseline lexical mạnh" bao gồm biến thể cặp source-sink. Chưa cam kết tường minh ⇒ chỉ mitigate. |
| ATK-05 | **MITIGATE** | Mục 9 đã **tự nhận** rủi ro benign mất cân bằng và FPR; nhưng chưa có thủ tục. |
| ATK-06 | **MITIGATE** | Mục 6 đã pre-commit dedup theo hash chuẩn hoá + chia theo cụm + MWF held-out; đây là thiết kế đúng hướng. |
| ATK-07 | **MITIGATE** | Cơ chế mô tả rõ ý tưởng (link-prediction từ seed); well-posed-hoá là việc viết, effort S. |
| ATK-08 | **MITIGATE** | Mỗi tầng ánh xạ một chế độ webshell (obfuscation trong-câu / source→sink trong-hàm / đa-file). Nhưng "cần" phải chứng minh bằng ablation (đã kế hoạch). |
| ATK-09 | **MITIGATE** | Mục 7 đã đặt FPR làm trục chính; bổ sung PR-AUC/MCC ở base-rate là việc nhỏ. |
| ATK-10 | **MITIGATE** | Mục 6 nêu ý định script + hash registry; chỉ cần nâng thành ledger đầy đủ. |

### Steelman của Blue

> *Đây là đề cương hiếm hoi đặt-claim có kỷ luật: nó giải quyết một chế độ lỗi thật (obfuscation phá tín hiệu từ vựng), chọn một bất biến cấu trúc đúng (source→sink), tránh mọi claim hiệu năng không-thể-giữ, và đã tự-liệt-kê hạn chế + pre-commit ablation/cross-dataset/FPR. Thiếu sót là của một bản nháp chưa chạy, không phải lỗi logic: demand chưa trích nguồn, delta novelty chưa định lượng, RQ chưa thao-tác-hoá. Cả ba đều fix-được-bằng-planning trước khi code.*

### Danh sách CONCEDE bắt buộc (kiểm V-A1, V-A7)

- **ATK-02 (Major)** — nhượng bộ toàn phần.
- **ATK-03 (Major)** — nhượng bộ toàn phần.

✔ Cả hai CONCEDE nằm trên finding ≥ Major ⇒ **không** kích `TOKEN-CONCESSION`.

---

# §7. ADJUDICATION LEDGER

| ATK | Phán quyết | Severity chốt | Mẩu bằng chứng quyết định |
|---|---|---|---|
| ATK-01 | **UPHELD** | Major | Mục 1 tự mô tả là "hợp nhất hai công trình đã có"; không có neo prior-art webshell-graph nào trong C5 để xác lập delta. `AP-07`. |
| ATK-02 | **UPHELD** (CONCEDE) | Major | C10 = 0 E1/E2/E3 có DOI; mốc thời sự chưa nguồn. |
| ATK-03 | **UPHELD** (CONCEDE) | Major | Không tồn tại câu C11 trong phác thảo; RQ Mục 7 không kèm tiêu chí bác bỏ. |
| ATK-04 | **DOWNGRADED** → Minor | Minor | Baseline CodeBERT/GCN có mặt; thiếu mỗi biến thể "token + cặp source-sink" — bổ sung dễ. |
| ATK-05 | **UPHELD** | Major | Mục 6 không có thủ tục lấy mẫu/nhãn benign; construct validity của FPR chưa thiết lập. |
| ATK-06 | **UPHELD** | Major | Bảng Mục 6: tổng ~7–8k, 2015–2022, tự ghi "trùng lặp/nhiễu"; chỉ 1 tập held-out. |
| ATK-07 | **UPHELD** | Major | Mục 3/5 mô tả predictor ở mức ý tưởng; chưa định nghĩa seed-set, negative sampling, τ, hàm mục tiêu ⇒ FR6 PARTIAL. |
| ATK-08 | **DOWNGRADED** → Major-thành-phần | Major | Ablation đã kế hoạch (RQ4) nhưng "cần" chưa chứng minh; `AP-13`-risk. Giữ ảnh hưởng lên W2. |
| ATK-09 | **UPHELD** | Major | Mục 7 chưa cam kết PR-AUC/MCC + FPR ở base-rate thực (webshell prevalence rất thấp). |
| ATK-10 | **DOWNGRADED** → Minor | Minor | Ý định reproducibility có; chỉ cần cụ thể hoá thành ledger. |

**Không có phán quyết `CONTESTED`.**

---

# §8. WORTH SCORECARD

| Chiều | Trọng số | Điểm | Neo so sánh / lý do | Tin cậy |
|---|---|---|---|---|
| **W1 Demand** | 32,5 | **2** | Trần thực tế E5 ⇒ luật cứng là ≤1; nâng lên **2** với ghi chú "sẽ mở tới 3 ngay khi trích ≥1 survey webshell (E3)". Lĩnh vực webshell quan trọng thật, nhưng **khoảng trống cụ thể** tự-tuyên-bố (technique-driven). T9 FAIL (không ánh xạ OWASP/ASVS). `AP-09`-nhẹ | TRUNG BÌNH |
| **W2 Novelty** | 22,5 | **2** | Không đạt 3: novelty = composition (T-CFBG ⊕ LOGWAT) + áp miền mới. Mảnh *thật-sự-mới* là Learned Taint-Dependency Predictor cho webshell — nhưng **delta so với webshell-graph detectors đã công bố chưa xác lập**, chưa quét bão hoà. `AP-07` | TRUNG BÌNH |
| **W3 Impact** | 25 | **2** | Không đạt 3: phát hiện webshell có giá trị vận hành thật (CI/CD, điều tra), và đề cương đặt FPR làm trục — nhưng **chưa có kết quả** cho thấy đổi quyết định của đội vận hành so với alternative mạnh nhất; T4 dừng ở nấc 2 | TRUNG BÌNH |
| **W4 Durability** | 10 | **1** | Có nhắc, không bằng chứng: luận điểm "source→sink bền hơn lexical" hợp lý nhưng danh sách seed source/sink gắn cú pháp PHP hiện hành, cần bảo trì; T6 chưa có bằng chứng độ bền | TRUNG BÌNH |
| **W5 Fit** | 10 | **3** | **Neo**: IJIS (Springer 10207) có lịch sử đăng ML cho phát hiện web attack/malware/intrusion — scope khớp trực tiếp. (Cần xác minh ≥3 bài cụ thể để nâng tin cậy T15) | TRUNG BÌNH |

**`Worth = (2×32,5 + 2×22,5 + 2×25 + 1×10 + 3×10)/5 = 200/5 = 40,0`**
**Band: THẤP.** Biên độ điểm trong họ = 2 (1→3) ✔ (thoả V-C3).

---

# §9. FEASIBILITY SCORECARD

| Chiều | Trọng số | Điểm | Neo / lý do | Tin cậy |
|---|---|---|---|---|
| **F1 Falsifiability** | 19 | **2** | RQ1–RQ5 **có** (hơn hẳn trạng thái "không RQ"), nhưng **thiếu C11** và khung chỉ-thuận (T19/T2 chưa có nhánh bất lợi). Nâng từ 1→2 nhờ RQ tồn tại + ablation kế hoạch | CAO |
| **F2 Construct/Validity** | 21 | **2** | `min(bốn loại)`. conclusion: kế hoạch ≥5 seed + mean±sd (tốt). internal: ablation kế hoạch (tốt) nhưng chưa chạy. **construct = 2**: dùng FPR (đúng hướng) nhưng nhãn benign chưa định nghĩa. **external = 2**: 5 tập nhỏ/cũ, 1 held-out. Loại yếu nhất kéo xuống 2 | TRUNG BÌNH |
| **F3 Baseline** | 20 | **2** | Baseline **có tên** + kế hoạch "cùng split"; chưa cấu hình/chưa chạy, chưa cam kết chạy mọi baseline trên cùng đồ thị. `V3` không kích (có nêu tên) | TRUNG BÌNH |
| **F4 Resource** | 15 | **4** | **Neo**: pipeline parse PHP (AST/CFG/DFG) rẻ; dataset nhỏ; compute khiêm tốn — nhóm đã chứng minh khả thi với LOGWAT/T-CFBG trên 1 GPU. Chiều mạnh nhất, chịu được phản biện thông thường | CAO |
| **F5 Threat model** | 7 | **2** | C6 **PARTIAL** (có adversary capability + trust boundary + loại trừ gradient-based tường minh). Hơn hẳn trạng thái vắng; nhưng security goal/assumption-set mỏng. Không `AP-10` cứng | TRUNG BÌNH |
| **F6 Assurance Fit** | 7,5 | **2** | Tier yêu cầu = A0 + kỷ luật thực nghiệm; đề cương **đã khai** kỷ luật đó (ablation/cross-dataset/seed) ⇒ **không `AP-17`, V7 KHÔNG kích**. Predictor chưa well-posed (FR6 PARTIAL) giữ điểm ở 2. Peer-norm `INSUFFICIENT` (chưa trích đủ bài IJIS) | THẤP (peer-norm) / TRUNG BÌNH |
| **F7 Ethics** | 4,5 | **3** | Dữ liệu công khai, phòng thủ, không human subject; dual-use tối thiểu (chỉ phát hiện, **từ chối tạo payload**) | CAO |
| **F8 Artifact** | 6 | **2** | Pre-commit script + hash registry (hơn 0), nhưng chưa có ledger (seed/version/hw/hash/README/container) | TRUNG BÌNH |

**`Feasibility = (2×19 + 2×21 + 2×20 + 4×15 + 2×7 + 2×7,5 + 3×4,5 + 2×6)/5`**
**`= (38 + 42 + 40 + 60 + 14 + 15 + 13,5 + 12)/5 = 234,5/5 = 46,9`**
**Band: THẤP (sát ngưỡng 50).** Biên độ điểm trong họ = 2 (2→4) ✔.

---

# §10. VETO CHECK

| ID | Điều kiện | Kích? | Hệ quả |
|---|---|---|---|
| V1 | Demand chỉ ở E5 | **KÍCH-nhẹ** | Hiện C10 toàn E5 ⇒ về lý thuyết `Worth ≤ 25`; **hoãn áp cứng** vì đây là đề cương và demand E3 bổ sung được với effort S — ghi là **điều-kiện-tiền-đăng-ký** (phải trích E3 trước khi nộp), không triệt tiêu dự án. *Nếu giữ nguyên không trích gì → V1 áp cứng, Worth ≤ 25.* |
| V2 | C11 trống | **KHÔNG áp cứng** | C11 là slot *đề-xuất*; MISSING → advisory; nhưng là đầu vào V10 |
| V3 | Không baseline nêu tên | **KHÔNG** | Baseline có tên (Mục 7) |
| V4 | RQ đã bị trả lời bởi công trình VERIFIED | **KHÔNG** | Chưa quét bão hoà; chưa thấy công trình subsuming VERIFIED ⇒ không ABANDON (V-A7) |
| V5 | Rào pháp lý/đạo đức | **KHÔNG** | — |
| V6 | >70% ngân sách tiêu trước khi biết "không" | **KHÔNG áp** | C12 MISSING → AF-10 |
| V7 | `AP-17` trên claim trung tâm | **KHÔNG** ✅ | Claim trung tâm *có* khai phương pháp kiểm (ablation/held-out) ⇒ không assurance-gap |
| V8 | C14 trống | **KHÔNG** | C14 PARTIAL |
| **V9** | Claim hiệu năng ≤ sàn vật lý | **KHÔNG** ✅ | **Không có claim latency/throughput nào** ⇒ FR1 sạch. Khác biệt cốt lõi so với bài "real-time" |
| V10 | Claim thực nghiệm trung tâm **vừa** thiếu C11 **vừa** directional-framing | **KÍCH (nhẹ)** ⚠️ | C11 vắng + chưa có nhánh bất lợi ⇒ `F1 ≤ 2` (đã thoả: F1 = 2). Không kéo thêm vì chưa có số liệu thiên lệch *đã công bố* (khác LOGWAT) |

**Ghi chú.** Không có veto nào *giết* dự án. V1 và V10 là **điều-kiện-tiền-đăng-ký** (fix trước khi code/nộp), đúng tinh thần shift-left. Vì không veto nào dẫn, §18 được quyết bằng **band + finding** dưới kiểm FRAGILE.

---

# §11. STRESS-TEST RESULTS (trích)

| ID | Người chạy | Kết quả | Lập luận | Severity |
|---|---|---|---|---|
| T1 Solutionism Inversion | Red | **FAIL-nhẹ** | Xoá "Graph-Transformer/GNN": còn "liên kết source→sink trong file để phát hiện webshell" — vẫn có nghĩa, nhưng khoảng trống định nghĩa bằng vắng-kỹ-thuật (Mục 1–2) | `W1 ≤ 2` |
| T2 Null-Result | Red | **FAIL** | Abstract giả định "E_sem không cải thiện" chưa công bố được: thiếu C11 + ablation chưa chạy | `F1 ≤ 2` |
| T3 Substitution | Red | **FAIL-nhẹ** | Chưa loại biến thể đơn giản nhất (Bi-LSTM/CodeBERT + cặp source-sink) | `W2 ≤ 2` |
| T4 So-What | Red | **FAIL** ở nấc 2 | "F1 cao hơn" → "bắt thêm webshell" → **dừng**: chưa có base-rate/PR-AUC để chứng đổi quyết định vận hành | `W3 ≤ 2` |
| T6 Durability | Red | **FAIL** | Seed source/sink gắn cú pháp PHP hiện hành | `W4 ≤ 2` |
| T7 Baseline Fairness | Red | **PARTIAL** | Có kế hoạch "cùng split" nhưng chưa cam kết cùng-đồ-thị/cùng-tuning | `F3 ≤ 2` |
| T9 Standards Anchor | Red | **FAIL** | Chưa ánh xạ OWASP ASVS/Testing Guide/CWE-webshell nào | `W1 ≤ 3` |
| T11 Necessity | Red | **PARTIAL** | 3 tầng + predictor + inter-proc: "cần" chưa chứng minh (ablation kế hoạch) | `W2 ≤ 3`, `AP-13`-risk |
| T12 Third-Party Restatement | ADJ | **FAIL** | Xem dưới | `W1 ≤ 2`, `AP-14` |
| **T17** Physical-Plausibility | ADJ | **N/A (PASS)** ✅ | **Không claim hiệu năng** ⇒ không có sàn để vi phạm. Đây là điểm sạch nhất của đề cương | — |
| **T18** 4PV | ADJ | **PRE-COMMIT PARTIAL** | Metric có P1/P2/P3-plan; **P4 independent-calc** chưa khai cho từng metric | Major (planning) |
| **T19** Directional-Framing | Red | **FAIL** | Thiếu nhánh bất lợi + C11 | `V10`, `AP-20` |
| **T20** Ablation Pre-Reg | ADJ | **PRE-COMMITTED** ✅ | K thành phần ⇒ RQ4 hứa ablation; cần liệt kê đúng K dòng | Minor |
| **T21** Reproducibility | ADJ | **PARTIAL** | Ý định có; ledger chưa đủ | Minor→Major |
| **T22** Formal-Object | ADJ | **FAIL** | Predictor + hàm taint chưa well-posed (seed/negative/τ/Validity) | Major kéo F6 |

### T12 — Phát biểu lại của bên thứ ba (chỉ dùng C10)

> *"Hiện chưa có trong đề cương một điều khoản tiêu chuẩn, một CVE, hay một số liệu sự cố nào cho thấy một bên vận hành cụ thể đang chịu thiệt hại vì thiếu đúng loại bộ phát hiện này."*
>
> *"Lĩnh vực webshell quan trọng là điều ai cũng công nhận, nhưng tầm quan trọng của khoảng trống kỹ thuật cụ thể mà đề cương nhắm tới hiện chỉ dựa trên phán đoán của tác giả."*

**Kết luận T12:** chưa xác lập bên hưởng lợi cụ thể / quyết định sẽ đổi. FAIL, `AP-14` — **fix bằng trích E1/E3**, effort S.

---

# §12. STRENGTHS REGISTER

| ID | Ưu điểm | Bằng chứng | Trục | Điều kiện phá vỡ | Độ hiếm |
|---|---|---|---|---|---|
| **RQS-01** | Chẩn đoán chế độ lỗi chính xác: obfuscation phá tín hiệu từ vựng, source→sink là bất biến đúng để bám | Mục 1, 5 | W2, W3 | Bị phá nếu ablation cho thấy **E_dfg một mình** đã đủ, khiến E_sem thừa; hoặc Bi-LSTM+cặp source-sink đạt tương đương (T3) | Trung bình |
| **RQS-02** | **Kỷ luật đặt-claim**: KHÔNG có claim latency ⇒ tránh nguyên lớp `PHYSICS_VIOLATION`/V9 | Toàn phác thảo (vắng mặt claim latency) | F-hiệu-năng, Forensic | Bị phá chỉ nếu bản viết sau *thêm* claim "real-time" không có budget | **Cao** — hiếm; nhiều bài cùng dòng chết đúng ở đây |
| **RQS-03** | Pre-commit forensic mạnh: ablation (RQ4), cross-dataset held-out (MWF), FPR-centric, ≥5 seed, dedup theo cụm | Mục 6, 7 | F1, F2, F8 | Bị phá nếu các cam kết này không được thực thi khi viết | Trung bình |
| **RQS-04** | Tự-liệt-kê Limitations + Threats to Validity ngay từ đề cương | Mục 9 | F2, C9 | — | Trung bình — hiếm ở giai đoạn đề cương |

---

# §13. FINDINGS REGISTER

| ID | Sev. | Trục | Bằng chứng | Tác động | Remedy | Effort | ATK | Mã forensic |
|---|---|---|---|---|---|---|---|---|
| **RQF-01** | **Major** | W1 | C10 = 0 E1/E2/E3; mốc 21/10/2026 chưa nguồn | Demand tự-tuyên-bố; trần W1 bị chặn; V1 treo | Trích ≥1 **E3** (survey webshell) + ≥1 **E1** (OWASP Testing Guide/ASVS, CWE-webshell/RCE) có DOI/URL; nếu có, 1 **E2** (báo cáo sự cố/CVE liên quan webshell) | **S** | ATK-02 | `SCOPE_INFLATION`-nhẹ |
| **RQF-02** | **Major** | W2 | Mục 1 "hợp nhất hai công trình đã có"; C5 thiếu prior-art webshell-graph | Novelty-by-composition; delta chưa xác lập | Quét bão hoà (DBLP/ACM/IEEE/Scopus) các bộ **webshell detection dựa đồ thị AST/opcode**; lập bảng delta số; định vị Learned Taint-Dependency Predictor là điểm mới neo được | **M** | ATK-01 | — |
| **RQF-03** | **Major** | F1 | Mục 7 RQ không kèm tiêu chí bác bỏ; thiếu nhánh bất lợi | `V10`; khung chỉ-thuận | Viết **C11** tường minh (vd "coi là KHÔNG nếu −E_sem < 0,5 pp macro-F1 ở mọi mức obfuscation, CI 95% chồng lấn"); thêm nhánh báo cáo kết quả bất lợi | **S** | ATK-03 | `DIRECTIONAL_ERROR` |
| **RQF-04** | **Major** | F2-construct | Mục 6 "benign lấy từ mã PHP sạch" — chưa thủ tục | FPR/construct chưa thiết lập; code CMS hợp lệ dễ gây FP | Khai thủ tục lấy mẫu/nhãn benign; báo tỉ lệ lớp; báo kết quả trên subset benign "khó" (framework dùng call_user_func) | **M** | ATK-05 | `DATA_LEAKAGE`-liên-quan |
| **RQF-05** | **Major** | F2-external | Mục 6: ~7–8k mẫu, 2015–2022, trùng lặp; 1 held-out | Khái quát hạn chế; rủi ro near-duplicate leakage | Dedup **mức nguồn** (payload gốc không nằm hai phía); thêm ≥1 cross-dataset thứ hai nếu tìm được; báo near-dup cluster | **M** | ATK-06 | `DATA_LEAKAGE` |
| **RQF-06** | **Major** | F6/FR6 | Mục 3/5: predictor + hàm taint chưa well-posed | Đối tượng hình thức mơ hồ (seed/negative/τ/Validity) | Định nghĩa: tập seed source/sink PHP; thủ tục negative sampling; hàm huấn luyện (BCE); cách hiệu chỉnh τ; cửa sổ CFG/DFG cho cặp ứng viên | **S–M** | ATK-07 | `PROPERTY_TYPE_MISMATCH`-risk |
| **RQF-07** | **Major** | W3/F2-ext | Mục 7 chưa cam kết base-rate/PR-AUC | Claim triển khai dễ bị base-rate bác | Cam kết báo **PR-AUC, MCC, FPR ở ≥3 base-rate** (vd 1% / 0,1% / 0,01%); định vị là nghiên cứu phát hiện, không hứa prod-precision | **S** | ATK-09 | — |
| **RQF-08** | **Minor** | F3 | Mục 7 baseline chưa cấu hình | So sánh có thể bất đối xứng | Cam kết chạy **mọi** baseline trên cùng biểu diễn đồ thị token + cùng ngân sách tuning; thêm biến thể "token + cặp source-sink" | **S** | ATK-04 | `MISSING_BASELINE`-risk |
| **RQF-09** | **Minor** | F8 | Mục 6 ý định script/registry | Chưa tái lập được | Ledger: seed · version (PyTorch/PyG) · spec HW · link+hash 5 dataset · repo+README+CI · container; Data Availability statement của Springer | **S–M** | ATK-10 | `REPRODUCIBILITY_GAP` |
| **RQF-10** | **Minor** | T11/W2 | Mục 4: 6 thành phần | "Cần" chưa chứng minh | Liệt kê đúng **K dòng ablation** (−Token-Transformer, −E_sem, −E_dfg, −inter-proc, −global-feat, −taint-predictor), mỗi dòng ≥5 seed | **S** (kế hoạch) | ATK-08 | `MISSING_ABLATION`-risk |

**Advisory (NON-BLOCKING).**
- A-1: C7-resource/C12 MISSING — bình thường với đề cương.
- A-2: Bổ sung ≥3 tài liệu IJIS 2022–2026 vào C5 để cố định peer-norm (OQ-5).

---

# §14. TRACEABILITY MATRIX

| RQ | Contribution | Method | Metric | Baseline | Assurance | Trạng thái |
|---|---|---|---|---|---|---|
| RQ1 | Đồ thị phân cấp HiPaG | 3 tầng + Graph-Transformer | Acc/F1/FPR | opcode+CNN, LOGWAT-style, CodeBERT | A0+kỷ luật | **OK-trên-kế-hoạch** (chưa chạy) |
| RQ2 | Kháng obfuscation | ma trận obfuscation held-out | F1 theo mức nhiễu | baseline lexical | A0 | **PARTIAL** — chưa thao-tác-hoá thang obfuscation |
| RQ3 | Tổng quát cross-dataset | MWF held-out | F1 | — | A0 | **OK-trên-kế-hoạch** |
| RQ4 | Ablation 6 thành phần | −từng thành phần | ΔF1 ± sd | — | A0 | **OK-trên-kế-hoạch** |
| RQ5 | Chi phí | thời gian suy luận | — | — | A0 | **OK** (không claim sàn ⇒ không V9) |
| — | Learned Taint-Dependency Predictor | link-prediction | AUC cạnh / độ phủ | luật cứng | — | **BROKEN** — chưa well-posed + chưa metric độ phủ |

**5/6 mắt xích OK-trên-kế-hoạch; 1 BROKEN (predictor).** Khác với trạng thái "0 RQ" của một bài không có research question — ở đây RQ-set **tồn tại và phủ hết contribution**, chỉ cần thao-tác-hoá + well-pose predictor.

---

# §15. PRIOR ART + SATURATION LOG

**Tuyên bố bão hoà: CHƯA ĐẠT.** Đề cương **chưa quét** prior-art webshell-graph một cách hệ thống.

| Nhóm công trình cần quét | Vì sao bắt buộc |
|---|---|
| Webshell detection dựa opcode + CNN/attention | Baseline trực tiếp + định vị delta (thay thế "luận án Lê Viết Hà" đã gỡ vì chưa công bố) |
| Webshell/malware PHP dựa **AST-GCN / CFG-GNN** | **Đối thủ novelty gần nhất** — nếu đã có đồ thị AST cho webshell, delta của HiPaG = phân cấp + taint-predictor, phải định lượng |
| Graph-Transformer nền (UniMP/TransformerConv, GATv2, SEAL link-prediction) | Nền kỹ thuật tái dùng — DISTINCT (không delta kiến trúc) |
| Taint analysis tĩnh PHP (RIPS, Pixy) | Nền source→sink — DISTINCT nhưng phải trích |

**Hệ quả:** **V4 không kích** (chưa thấy subsuming VERIFIED), nhưng W2 bị giữ ở 2 cho tới khi quét bão hoà + xác lập delta. Đây là **Open Question BLOCKING** (OQ-1).

---

# §16. REFORMULATED RQ CANDIDATES

Đề cương **có** RQ1–RQ5; vấn đề là **thao-tác-hoá** và **thêm trục bác bỏ**, không phải viết mới từ đầu.

### RQ-A *(khuyến nghị — hẹp nhất, khả nghiệm nhất; tinh chỉnh RQ2+RQ4)*

> *"Trong phát hiện webshell PHP, việc bổ sung cạnh ngữ nghĩa source→sink học được (E_sem) vào đồ thị đã có E_seq/E_skip/E_cfg/E_dfg đóng góp bao nhiêu vào macro-F1 và FPR, và phần đóng góp đó thay đổi thế nào khi mức obfuscation (0/base64/gzinflate/variable-function/đa-lớp) tăng?"*

- **(a) Lý do:** cô lập đúng đóng góp mới nhất (taint-predictor) và biến **obfuscation thành biến độc lập có thang đo** thay vì tính từ.
- **(b) Kéo theo:** cần ablation −E_sem; sinh test phân tầng theo mức obfuscation; C11 = *"coi là KHÔNG nếu −E_sem làm macro-F1 giảm <0,5 pp ở mọi mức, CI 95% chồng lấn"*.
- **(c) Điểm dự kiến sau sửa:** F1 2→3, F2-internal 2→3 ⇒ Feasibility ≈ 52.

### RQ-B *(trục cross-architecture / zero-day webshell; tinh chỉnh RQ3)*

> *"Mô hình HiPaG có duy trì độ chính xác trên webshell mà bảng seed taint **không** phủ (họ/biến thể mới), so với trên webshell được phủ, và khoảng cách đó so với baseline lexical ra sao?"*

- **(a) Lý do:** phép thử trực tiếp cho claim "bắt cái luật cứng bỏ sót".
- **(b) Kéo theo:** phân tách test theo độ phủ seed; cross-dataset MWF; báo cả nhánh bất lợi (chống AP-20).
- **(c) Điểm dự kiến:** W2 2→3, F1 2→3 ⇒ Worth ≈ 45, Feasibility ≈ 52.

### RQ-C *(trục vận hành; cứu claim triển khai)*

> *"Ở tỉ lệ webshell hiện thực (0,01%–1% file), HiPaG đạt đường PR nào, và với ngân sách cảnh báo giả cho trước, recall tối đa so với YARA/php-malware-finder là bao nhiêu?"*

- **(b) Kéo theo:** báo PR-AUC/MCC thay accuracy; thêm baseline luật tĩnh (YARA + php-malware-finder).
- **(c) Điểm dự kiến:** W3 2→3 ⇒ Worth ≈ 45.

---

# §17. Q1 UPGRADE PLAN *(xếp giảm dần theo Δđiểm/effort)*

| # | Hành động | Đóng finding | Trục | Δđiểm | Effort | Phụ thuộc | Bắt buộc Q1? |
|---|---|---|---|---|---|---|---|
| 1 | Trích **E1 (OWASP/CWE webshell/RCE) + E3 (≥1 survey webshell)** có DOI vào C10/Related Work | RQF-01 | W1 | +4 | **S** | — | **CÓ** |
| 2 | Viết **C11** tường minh + thêm nhánh kết quả bất lợi | RQF-03 | F1 | +3 | **S** | — | **CÓ** |
| 3 | Quét bão hoà **webshell-graph (AST-GCN/CFG-GNN)** + bảng delta số | RQF-02 | W2 | +4 | **M** | — | **CÓ** |
| 4 | Well-pose **Learned Taint-Dependency Predictor** (seed/negative/τ/hàm mục tiêu/cửa sổ) | RQF-06 | F6 | +2 | **S–M** | — | **CÓ** |
| 5 | Khai thủ tục lấy mẫu/nhãn **benign** + tỉ lệ lớp + subset benign khó | RQF-04 | F2 | +3 | **M** | — | **CÓ** |
| 6 | Dedup **mức nguồn** + near-dup cluster split; thêm cross-dataset #2 nếu có | RQF-05 | F2-ext | +3 | **M** | — | **CÓ** |
| 7 | Cam kết **PR-AUC/MCC/FPR ở ≥3 base-rate** + baseline luật tĩnh (YARA) | RQF-07 | W3, F2 | +3 | **S–M** | — | **CÓ** |
| 8 | Liệt kê đúng **K dòng ablation** (6 thành phần) ≥5 seed | RQF-10 | F2-int, W2 | +4 | **S** (kế hoạch) | 4 | **CÓ** |
| 9 | Cam kết chạy **mọi baseline cùng biểu diễn + cùng tuning** + biến thể cặp source-sink | RQF-08 | F3 | +3 | **M** | — | **CÓ** |
| 10 | **Reproducibility ledger** + Data Availability statement | RQF-09 | F8 | +2 | **S–M** | — | **CÓ** |
| 11 | Thao-tác-hoá **thang mức obfuscation** cho RQ2 (0/5/10/20 hoặc theo kỹ thuật) | RQF-03 | W2, F1 | +3 | **M** | 2, 4 | Nên |
| 12 | Bổ sung ≥3 ref IJIS 2022–2026 (cố định peer-norm) | A-2 | W5, F6 | +1 | **S** | — | Nên |

### Ba tầng

| Tầng | Nội dung | Tổng effort | Điểm dự kiến sau tầng |
|---|---|---|---|
| **T1 — Bắt buộc** (đóng mọi Major + điều-kiện-tiền-đăng-ký V1/V10) | #1–#10 | ≈ **4–7 tuần-người** (phần lớn là viết/pre-register, chưa tính chạy) | Worth ≈ 46 · Feasibility ≈ 56 |
| **T2 — Đạt chuẩn Q1** (chạy thí nghiệm theo kế hoạch đã pre-register) | + #11, #12 + thực thi toàn bộ ablation/cross-dataset/obfuscation | ≈ **+8–12 tuần-người** | Worth ≈ 52 · Feasibility ≈ 64 |
| **T3 — Nổi bật** | + adaptive-adversary eval (nối sang bài graph-attack), artifact badged, cross-language Python | ≈ **+8–10 tuần-người** | Worth ≈ 58 · Feasibility ≈ 70 |

**Cảnh báo cấu trúc.** Trần Worth bị chặn bởi **W1 (demand)** và **W2 (novelty-delta)**. Hành động #1 và #3 là **đòn bẩy rẻ nhất**: không trích E1/E3 và không xác lập delta thì dù thí nghiệm có đẹp đến đâu, Worth vẫn mắc ở band Thấp–Trung-bình-thấp. Làm #1–#3 **trước** khi đổ 10+ tuần-người vào T2.

---

# §18. FINAL DETERMINATION

## (a) Ô ma trận

| Feasibility ↓ \ Worth → | Worth <50 (**40**) |
|---|---|
| **Feas <50 (47)** | **TỪ BỎ** *(ô danh nghĩa)* |

### **KẾT LUẬN: `TỪ BỎ cách-đặt-vấn-đề-hiện-tại` ⇒ thực chất `RESCOPE`.**

Giải thích rạch ròi (đây là điểm then chốt, khác hẳn một verdict TỪ BỎ do số liệu hỏng):

1. **Không veto nào giết dự án.** V9 (physics) KHÔNG kích vì không có claim latency; V7 (assurance-gap) KHÔNG kích vì claim trung tâm có khai phương pháp kiểm; V4 (đã-bị-trả-lời) KHÔNG kích. Chỉ V1/V10 kích ở dạng **điều-kiện-tiền-đăng-ký**, fix-được-bằng-planning.
2. **Cả hai band ở vùng FRAGILE** (Feas 47 cách ngưỡng 3 điểm; cờ `FRAGILE-BAND` đã bật). Theo V-C6/V-C7, §18 **không** được quyết bằng con số trong vùng này mà bằng finding + veto. Không veto giết ⇒ ô danh nghĩa "TỪ BỎ" **không** phản ánh đúng; verdict hành-động-đúng là **RESCOPE**: giữ cơ chế, đóng các điều-kiện-tiền-đăng-ký (#1–#10 §17) **trước khi** code.
3. **Cái bị "từ bỏ" là cách đặt vấn đề hiện tại** (demand tự-tuyên-bố + novelty chưa định lượng + RQ chưa thao-tác-hoá), **KHÔNG** phải ý tưởng. §16 mô tả đúng cùng cơ chế được dựng lại — nằm ở ô `RESCOPE`.

## (b) Q1 Readiness

**`Q1-REACHABLE`.** Khoảng cách tới chuẩn IJIS là **đóng-được-bằng-planning + thực-thi**, không có rào cấu trúc (không physics-violation, không số liệu mâu thuẫn — vì chưa có số liệu). Sau T1+T2 §17 (~12–19 tuần-người), IJIS là mục tiêu hợp lý.

## (c) Điều kiện chuyển band (kiểm nhị phân) — từ `RESCOPE` sang `TIẾN HÀNH`

1. C10 có ≥1 **E1** (OWASP/CWE webshell/RCE) **và** ≥1 **E3** (survey) xác minh được. `[CÓ/KHÔNG]`
2. Có bảng **delta số** so với ≥2 bộ webshell-graph đã công bố (quét bão hoà xong). `[CÓ/KHÔNG]`
3. Có câu **C11** tường minh + ≥1 nhánh báo cáo kết quả bất lợi. `[CÓ/KHÔNG]`
4. Learned Taint-Dependency Predictor **well-posed** (seed/negative/τ/hàm mục tiêu định nghĩa). `[CÓ/KHÔNG]`
5. Thủ tục nhãn **benign** + tỉ lệ lớp + dedup mức nguồn được công bố. `[CÓ/KHÔNG]`
6. Kế hoạch **6 dòng ablation** ≥5 seed + mean±sd. `[CÓ/KHÔNG]`
7. Cam kết **PR-AUC/MCC/FPR ở ≥3 base-rate** + baseline luật tĩnh. `[CÓ/KHÔNG]`

## (d) Thời điểm sớm nhất biết câu trả lời là "không"

**Ngay sau ablation −E_sem (hành động #8, ~2–3 tuần-người sau khi pipeline chạy).** Nếu E_sem học được đóng góp <0,5 pp macro-F1 so với chỉ dùng E_cfg/E_dfg ở mọi mức obfuscation, thì đóng góp mới nhất của bài không tồn tại và nên rẽ hướng. Đây là thí nghiệm rẻ nhất có khả năng giết dự án — hãy chạy **trước** khi viết bản đầy đủ. Đề cương hiện đã pre-commit đúng thí nghiệm này (RQ4) — điểm cộng.

---

# §19. DISSENT RECORD

**Bất đồng chưa khép — ATK-01 (novelty).**

- **Red:** *"Phân cấp là của T-CFBG, đa quan hệ là của LOGWAT; HiPaG chỉ đổi miền sang PHP. Novelty-by-composition, W2 ≤ 2 cho tới khi có delta số so với webshell-graph đã công bố."*
- **Blue:** *"Learned Taint-Dependency Predictor **cho webshell** chưa có tiền lệ; source→sink học được khác hẳn 9-cặp luật cứng của LOGWAT và khác E_sem smart-contract của T-CFBG."*
- **ADJ:** `UPHELD` **có điều kiện** — Blue có lý về *bản chất* điểm mới, nhưng **không trích được** một bộ webshell-graph nào để chứng minh delta. Bất đồng khép được bằng **một việc**: quét bão hoà (OQ-1). Tới khi đó W2 giữ ở 2.

---

# §20. OPEN QUESTIONS

## BLOCKING

| # | Câu hỏi | Vì sao chặn |
|---|---|---|
| **OQ-1** | Đã có bộ phát hiện webshell dựa đồ thị AST/CFG-GNN nào công bố chưa, và delta số của HiPaG so với chúng là gì? | Quyết định W2 và định vị novelty. RQF-02 |
| **OQ-2** | Thủ tục lấy mẫu + gán nhãn "benign" là gì; tỉ lệ lớp bao nhiêu? | Quyết định construct validity của FPR. RQF-04 |
| **OQ-3** | Learned Taint-Dependency Predictor: seed source/sink chính xác, negative sampling, τ, hàm mục tiêu? | Well-posed đối tượng lõi. RQF-06 |
| **OQ-4** | Mốc 21/10/2026 là sự kiện cụ thể nào (nguồn)? Có ánh xạ được vào E1/E2 không? | Quyết định demand/động lực thời điểm. RQF-01, C13 |
| **OQ-5** | ≥3 bài IJIS 2022–2026 về phát hiện xâm nhập/malware/web attack để cố định peer-norm | T15/F6 hiện INSUFFICIENT |

## NON-BLOCKING

| # | Câu hỏi |
|---|---|
| OQ-6 | Thang "mức obfuscation" sẽ định nghĩa thế nào (theo số token nhiễu hay theo kỹ thuật)? |
| OQ-7 | Siêu tham số dự kiến (số tầng GAT, số head, hidden dim, δ của E_skip)? |
| OQ-8 | Có kế hoạch cross-language sang Python ở bản sau không (đã chuyển sang hướng mở rộng)? |

---

# §21. VERIFICATION REPORT

| Assertion | Kết quả | Ghi chú |
|---|---|---|
| V-S1 Đủ §0–§23, đúng thứ tự | **PASS** | — |
| V-S2 Bảng điền đủ / ghi INSUFFICIENT | **PASS** | Peer-norm đánh INSUFFICIENT (OQ-5) |
| V-P1 Mọi điểm ≥3 có neo | **PASS** | W5, F4 có neo (IJIS scope; prior pipeline nhóm). Tin cậy hạ nơi chưa xác minh bài cụ thể |
| V-P2 Không khẳng định mồ côi | **PASS** | Mọi khẳng định trỏ slot C |
| V-P3 Citation có DOI/URL hoặc UNVERIFIED | **PASS** | Chưa dùng citation nào để chấm ≥3 (nền nhóm là tự-trích, không neo điểm) |
| V-P4 Stale-finding guard | **PASS** | Neo text hiện tại của phác thảo (bản chốt scope PHP) |
| V-A1 Blue CONCEDE ≥1 | **PASS** | ATK-02, ATK-03 (Major) |
| V-A2 Red thừa nhận ≥1 ưu điểm | **PASS** | RQS-A, RQS-B |
| V-A3/A4 | **PASS** | 10/10 ATK có 1 phản hồi + 1 phán quyết kèm bằng chứng |
| V-A6 Finding truy về ATK | **PASS** | 10/10 |
| V-A7 CONCEDE ≥ Major; V4 chỉ VERIFIED | **PASS** | Hai CONCEDE Major; V4 không kích |
| V-C1 Hồ sơ trọng số §8/§9 = §3 | **PASS** | Trung bình P2×P3 |
| V-C2 Trọng số cộng 100 | **PASS** | W 100; F 100 |
| V-C3 Biên độ điểm >±1 | **PASS** | W: 1–3; F: 2–4 |
| V-C4 Veto áp lên số cuối | **PASS** | V1/V10 áp dạng điều-kiện; V9/V7 không kích |
| V-C5 Tính lại Σ/5 | **PASS** | Worth 40,0; Feasibility 46,9 |
| V-C6 Không phụ thuộc <10 điểm | **PASS** | Feas cách 50 chỉ 3 ⇒ quyết bằng finding, không số (→ RESCOPE) |
| V-C7 FRAGILE-BAND | **PASS** | Đã bật cờ; chuyển quyết định sang veto+finding |
| V-M2 §18 một kết luận | **PASS** | RESCOPE (TỪ BỎ cách-đặt-hiện-tại) |
| V-M6 RQ-set coherence | **PASS** | RQ1–RQ5 rời nhau, phủ hết contribution; predictor là mắt xích cần well-pose |
| V-M7 §22 có mặt, khớp §18, hạng khớp W2 | **PASS** | W2=2 ⇒ hạng `Marginal`, cấm Landmark |
| V-F1 Claim hiệu năng có sàn hoặc N/A | **PASS** | Không claim hiệu năng ⇒ N/A tường minh; V9 không kích |
| V-F3 Falsification hoặc V10 | **PASS** | V10 áp (C11 vắng) |
| V-F7 §23 có mặt, FR-band ≤ Feas band | **PASS** | GAPS-PLANNABLE ≥ (không lạc quan hơn Thấp? xem ghi chú §23) |
| V-F8 Guard trực giao Worth | **PASS** | §22/§17 KHÔNG viện forensic để cứu Worth |

**Tổng: toàn bộ assertion lõi PASS.** Khác biệt căn bản so với autopsy một manuscript hỏng: **0 FAIL loại forensic** (không có số liệu để mâu thuẫn, không claim để vi phạm sàn).

---

# §22. EXECUTIVE VERDICT (chốt hạ)

## (A) Nội dung (RQ/Contribution/method) có THỰC TẾ để TIẾN HÀNH không?

### **CÓ — CÓ ĐIỀU KIỆN.**

1. **RQ answerable trong nguồn lực đã khai.** Pipeline parse PHP rẻ, dataset nhỏ, compute khiêm tốn (F4 = 4); nhóm đã chứng minh khả thi với LOGWAT/T-CFBG. Không có rào tài nguyên.
2. **Baseline + assurance-plan đúng loại & khả thi.** Claim "tốt hơn baseline" cần A0 + kỷ luật thực nghiệm, và đề cương **đã pre-commit** đúng kỷ luật đó (ablation/cross-dataset/seed) ⇒ không assurance-gap, V7 không kích.
3. **Rào thực thi lớn nhất KHÔNG phải kỹ thuật mà là định vị:** (i) demand tự-tuyên-bố (chưa E1/E3); (ii) novelty-delta chưa xác lập (chưa quét webshell-graph). Cả hai là việc **đọc–trích–đối-chiếu**, effort S–M, phải làm **trước** khi code.
4. **Scoping bắt buộc để "CÓ" thành thật:** thu về **RQ-A** (đóng góp E_sem, đo bằng ablation, dưới obfuscation có thang đo) làm RQ xương sống; giữ RQ-B/RQ-C làm trục phụ; well-pose taint-predictor; viết C11.

## (B) CHẤT LƯỢNG & ĐÁNG LÀM?

| Chiều | Mức | Neo (1 câu) |
|---|---|---|
| **Học thuật** (rigor · novelty-delta · đúng-loại-assurance) | **Trung bình–Thấp** | Assurance đúng loại và pre-commit tốt, nhưng novelty = composition và delta so với webshell-graph chưa xác lập (W2 = 2) |
| **Khả thi** (= Feasibility §9 + veto) | **Trung bình–Thấp** (47, sát 50) | Không veto giết; F4 mạnh; các gap đều planning-fixable; FRAGILE sát ngưỡng |
| **Thực tiễn** (deploy? lợi thế so alternative mạnh nhất?) | **Trung bình** | Đặt FPR làm trục + định hướng CI/CD là đúng vận hành, nhưng chưa cam kết PR-AUC/base-rate và chưa so YARA/php-malware-finder |
| **Cần thiết** (demand E1–E3 · khẩn cấp?) | **Thấp (sửa được rẻ)** | C10 hiện toàn E5; webshell có E3 sẵn, chỉ cần trích |

- **ĐÁNG LÀM?** → **`ĐÁNG — CÓ ĐIỀU KIỆN`** (nhất quán ô §18 = RESCOPE). Cơ chế đáng theo đuổi; phải đóng demand + novelty-delta + RQ/C11 **trước** khi đổ công thí nghiệm.
- **Hạng đóng góp:** **`Marginal` → `Solid-incremental`-có-thể-đạt** (hiện W2 = 2 ⇒ Marginal; **cấm** Landmark vì novelty = composition). Lên Solid-incremental khi xác lập delta số (OQ-1) + đo được độ phủ taint-predictor.
- **Venue-target thực tế:** IJIS **đạt được** sau T1+T2 §17. Nếu chỉ làm T1, nhắm một tạp chí ứng dụng hạng giữa hoặc hội nghị chuyên đề an ninh trước.
- **Cảnh báo trung thực (≤2 câu):** Đây là bài **technique-driven** — khoảng trống hiện định nghĩa bằng vắng-mặt-kỹ-thuật, không bằng thiệt hại có hồ sơ; điểm mới nằm ở việc **ghép** hai khung sẵn có cộng một predictor chưa well-posed. Điểm mạnh hiếm: đề cương **không** mắc bẫy claim latency nên tránh được nguyên lớp lỗi vật lý mà các bài "real-time detector" thường chết.
- **Forensic-Readiness:** **`GAPS-PLANNABLE`** — manuscript hoàn thiện **có thể sống sót** OMNI-FORENSIC v2.0 **nếu** thực thi đúng các pre-commit; gate rủi ro lớn nhất là **FR7 (Citation-Support/novelty-delta)** và **FR2 (4PV — thêm đường P4 independent-calc cho mỗi metric)**, không phải FR1 (đã sạch).

---

# §23. FORENSIC-READINESS SCORECARD

*Câu hỏi: nếu dựng xong manuscript theo đề cương này, nó có sống sót OMNI-FORENSIC-AUDIT v2.0 không?*

| FR | Checkpoint | Trạng thái | Bằng chứng/kế hoạch | Rủi ro tồn dư | Hành động §17 |
|---|---|---|---|---|---|
| **FR1** Physical-Plausibility | RULE-2 | **PRE-COMMITTED** ✅ | **Không có claim hiệu năng** ⇒ không có sàn để vi phạm | Thấp — chỉ rủi ro nếu bản sau *thêm* claim latency không budget | (giữ nguyên: đừng thêm claim latency thiếu budget) |
| **FR2** Evidence-Path 4PV | RULE-3 | **PARTIAL** | Metric có P1/P2/P3-plan; thiếu **P4 independent-calc** per-metric | Mỗi số phải tự-tính-lại-được từ confusion matrix | #7 (báo đủ P/R/FPR để P4 kiểm chéo) |
| **FR3** Directional-Neutrality | RULE-4/9 | **ABSENT** | Chưa C11, chưa nhánh bất lợi | `DIRECTIONAL_ERROR` nếu không sửa | #2 |
| **FR4** Ablation/Delta | Khối 4.4 | **PRE-COMMITTED** ✅ | RQ4 hứa ablation 6 thành phần | Phải liệt kê đúng K dòng + ≥5 seed | #8 |
| **FR5** Reproducibility | Khối 4.3 | **PARTIAL** | Ý định script + hash registry | Thiếu ledger đầy đủ | #10 |
| **FR6** Formal-Object | RULE-5/6 | **ABSENT** | Predictor + hàm taint chưa well-posed | `PROPERTY_TYPE_MISMATCH`-risk | #4 |
| **FR7** Citation-Support | RULE-7 | **ABSENT** | Chưa quét prior-art, 0 DOI, delta chưa xác lập | `CITATION_MISMATCH`/novelty chưa neo | #1, #3 |
| **FR8** Domain-Forensic Hook (ML) | RULE-11 | **PARTIAL** | Có: FPR/held-out/dedup kế hoạch. Thiếu: thủ tục nhãn, MCC/AUC, kiểm leakage mức nguồn | `DATA_LEAKAGE`-risk | #5, #6 |

## **Forensic-Readiness band: `GAPS-PLANNABLE`**

**2/8 PRE-COMMITTED · 3/8 PARTIAL · 3/8 ABSENT; 0 gate ABSENT thuộc loại không-fix-được-bằng-planning; V9 KHÔNG kích.** Mọi gap đều có hành động §17 tương ứng và đều là việc làm **trước khi code** (shift-left). Đây là khác biệt hạng nặng so với một manuscript đã hỏng cấu trúc (`STRUCTURAL-RISK`): HiPaG chưa viết ra số nào để mâu thuẫn và chưa đặt claim nào để vi phạm sàn.

> **Guard trực-giao (Worth) — bắt buộc.** Forensic-Readiness tốt (`GAPS-PLANNABLE`) **KHÔNG** được dùng để nâng verdict §18. Verdict vẫn là **RESCOPE** do **Worth = 40** quyết định, và Worth chỉ nâng được bằng **#1 (trích E1/E3)** + **#3 (xác lập delta novelty)** — không bằng bất kỳ việc dọn forensic nào. "Làm có sạch" (FR tốt) khác "có đáng làm" (Worth). ✔ (V-F8)

---

## Tài liệu tham chiếu nội bộ (phiên audit)

- Phác thảo HiPaG (Claude Doc, bản chốt scope PHP 2026-10-23) — đối tượng audit.
- Protocol: OMNI_RQ_AUDIT v4.0 (file người dùng cung cấp).
- Nền nhóm (tự-trích, không dùng neo điểm): T-CFBG Graph-Transformer framework; LOGWAT multi-relational behavioral graph.

*Báo cáo tạo bởi OMNI_RQ_AUDIT v4.0 · MODE = EXTRACT_AND_AUDIT · STRICTNESS = Q1-hostile · PASS = FULL · VENUE = IJIS (Springer 10207) · 2026-10-23*
