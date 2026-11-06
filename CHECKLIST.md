# HiPaG — Checklist thực thi dự án (theo Bước)

> Bản 2026-11-06. 37 bước đánh số liền mạch. Mỗi bước = **việc cần làm + mục tiêu**.
> Ký hiệu: **[x] xong · [»] đang/kế tiếp · [ ] chưa**.

**► BƯỚC HIỆN TẠI: Bước 0 (dựng thư mục code trên máy).** Tiến độ: 3/37 + đang làm Bước 0.

*Chia việc (chung): Claude Code lo phần code/pipeline/train; Copilot lo phần viết LaTeX.*
*Vận hành: repo ở ổ WorkingD; git nội bộ, không push; Overleaf chỉ khi hoàn chỉnh; mọi số qua numbers.tex.*

---

## Bước 0 — Chuẩn bị (dựng thư mục code + môi trường)

- [»] **Bước 0 — Dựng khung thư mục code trên máy.** → *mục tiêu:* có repo chạy được tại chỗ.
  - Giải nén scaffold `hipag-webshell/` lên ổ WorkingD (đã có sẵn, không dựng lại từ đầu).
  - Tạo môi trường ảo + cài thư viện (`requirements.txt`).
  - Cài bộ phân tích PHP (nikic/PHP-Parser).
  - `git init` nội bộ + bật hook chặn file lớn/dữ liệu (không tạo remote, không push).
- [»] **Bước 0b — Dựng bộ khung bài báo tiếng Anh (`paper/main.tex`).** → *mục tiêu:* có bản phác thảo dạng paper (tiêu đề, abstract, các mục, khung kết quả) để viết dần; song song với phác thảo tiếng Việt trong Claude Doc. Mọi số qua `numbers.tex`.

**Mục tiêu Bước 0:** thư mục code + bộ khung paper sẵn sàng để bắt đầu Giai đoạn 0.

---

## ✅ Đã xong — Đóng Worth

- [x] **Bước 1 — Thu thập bằng chứng nhu cầu (demand).** → *mục tiêu:* chứng minh bài toán có người cần bằng nguồn ngoài (ATT&CK, CVE, OWASP, survey), không tự nói.
- [x] **Bước 2 — Quét công trình liên quan + xác định điểm mới.** → *mục tiêu:* biết đối thủ gần nhất (GlareShell) và HiPaG mới ở đâu.
- [x] **Bước 3 — Chốt tiêu đề + tạp chí đích.** → *mục tiêu:* có tiêu đề cuối cùng và xác nhận hợp IJIS.

---

## Giai đoạn 0 — Chốt thiết kế (trước khi code)

- [ ] **Bước 4 — Viết tiêu chí bác bỏ + nhánh kết quả bất lợi.** → *mục tiêu:* bài có thể "sai được", không chỉ thừa nhận kết quả thuận.
- [»] **Bước 5 — Định nghĩa đầy đủ bộ dự đoán cạnh taint source→sink.** → *mục tiêu:* chốt cách học cạnh ngữ nghĩa (seed, mẫu âm, ngưỡng, hàm mất mát) để code được.
- [ ] **Bước 6 — Chốt bộ chỉ số đánh giá.** → *mục tiêu:* thống nhất đo F1/MCC/PR-AUC/FPR và precision ở tỉ lệ thực, mỗi số tự kiểm lại được.
- [ ] **Bước 7 — Điền số kết quả của đối thủ từ bài gốc.** → *mục tiêu:* biết mốc GlareShell/AST-DF để so delta.

**Mục tiêu cả Giai đoạn 0:** mọi điều kiện tiên quyết để bắt tay đều đạt.

---

## Giai đoạn 1 — DATA (thu thập dữ liệu)

- [ ] **Bước 8 — Gộp 5 tập webshell + lọc PHP.** → *mục tiêu:* có tập webshell thô, đủ nhãn.
- [ ] **Bước 9 — Lấy mẫu lành tính + nhóm "lành tính khó".** → *mục tiêu:* tập benign minh bạch, có tỉ lệ lớp, đủ thử false positive.
- [ ] **Bước 10 — Khử trùng + gom cụm trùng lặp.** → *mục tiêu:* loại rò rỉ do mẫu na ná nhau.
- [ ] **Bước 11 — Chia train/val/test theo cụm, tách tập ngoài phân phối.** → *mục tiêu:* chia dữ liệu không rò rỉ; giữ một tập chưa từng train.
- [ ] **Bước 12 — Ghi dấu vết nguồn gốc dữ liệu.** → *mục tiêu:* tái lập được, chống tráo dữ liệu.

**Mục tiêu cả Giai đoạn 1:** mọi mẫu có nhãn và cụm; tập ngoài phân phối nằm ngoài train.

---

## Giai đoạn 2 — Phân tích (dựng biểu diễn + kiểm dữ liệu)

- [ ] **Bước 13 — Phân tích PHP ra cây cú pháp.** → *mục tiêu:* lấy được cấu trúc mã; ghi lại mẫu không phân tích được.
- [ ] **Bước 14 — Dựng đồ thị phân cấp (câu lệnh → hàm → file).** → *mục tiêu:* có biểu diễn đồ thị đa quan hệ cho mỗi file.
- [ ] **Bước 15 — Sinh cạnh taint source→sink học được.** → *mục tiêu:* đưa quan hệ ngữ nghĩa vào đồ thị.
- [ ] **Bước 16 — Tạo tập obfuscation nhiều mức (giữ riêng để test).** → *mục tiêu:* đo được khả năng kháng obfuscation theo thang.
- [ ] **Bước 17 — Chạy kiểm tra "lối tắt"/rò rỉ dữ liệu.** → *mục tiêu:* xác nhận dữ liệu không có đặc trưng nông ăn gian.

**Mục tiêu cả Giai đoạn 2:** đồ thị dựng xong toàn bộ; kiểm tra rò rỉ cho kết quả thấp (dữ liệu sạch).

---

## Giai đoạn 3 — Train (model + huấn luyện + đánh giá)

- [ ] **Bước 18 — Dựng mô hình 3 tầng + bộ dự đoán taint.** → *mục tiêu:* có kiến trúc chạy được.
- [ ] **Bước 19 — Dựng bộ nạp dữ liệu.** → *mục tiêu:* nạp đồ thị ổn định, không tràn bộ nhớ, chạy tiếp được khi dừng.
- [ ] **Bước 20 — Viết vòng huấn luyện.** → *mục tiêu:* train một hạt giống, lưu mô hình tốt nhất.
- [ ] **Bước 21 — Viết phần đánh giá + xuất số ra macro.** → *mục tiêu:* mọi số sinh tự động, đưa thẳng vào paper.
- [ ] **Bước 22 — Chạy ablation TRƯỚC (bỏ từng thành phần).** → *mục tiêu:* chứng minh cạnh taint thực sự đóng góp.
- [ ] **Bước 23 — So với các baseline (gồm GlareShell, YARA).** → *mục tiêu:* chứng minh HiPaG hơn, công bằng cùng điều kiện.
- [ ] **Bước 24 — Đánh giá kháng obfuscation theo mức.** → *mục tiêu:* cho thấy giữ hiệu năng khi mã bị che giấu.
- [ ] **Bước 25 — Đánh giá tổng quát trên tập ngoài phân phối.** → *mục tiêu:* chứng minh không học vẹt một tập.
- [ ] **Bước 26 — Gộp 5 hạt giống.** → *mục tiêu:* mọi bảng có trung bình ± độ lệch.

**Mục tiêu cả Giai đoạn 3:** mọi câu hỏi nghiên cứu có số liệu 5-seed; đã chạy GlareShell để chốt điểm mới bằng số.

---

## Giai đoạn 4 — Viết paper

- [ ] **Bước 27 — Dựng khung bài.** → *mục tiêu:* có bố cục đủ mục chuẩn Q1.
- [ ] **Bước 28 — Viết Mở đầu + Công trình liên quan.** → *mục tiêu:* trình bày nhu cầu và điểm mới có trích nguồn.
- [ ] **Bước 29 — Viết Phương pháp.** → *mục tiêu:* mô tả rõ 3 tầng + bộ dự đoán taint + hình kiến trúc.
- [ ] **Bước 30 — Viết Kết quả.** → *mục tiêu:* mọi số lấy từ macro, có bảng và hình.
- [ ] **Bước 31 — Viết Đe doạ tính hợp lệ + Mô hình kẻ tấn công.** → *mục tiêu:* trung thực về giới hạn.
- [ ] **Bước 32 — Viết mục công bố dữ liệu & mã.** → *mục tiêu:* đáp ứng yêu cầu tái lập của tạp chí.

**Mục tiêu cả Giai đoạn 4:** bản thảo không còn số gõ tay; biên dịch sạch.

---

## Giai đoạn 5 — Hoàn thiện dự án

- [ ] **Bước 33 — Lập hồ sơ tái lập.** → *mục tiêu:* ai cũng chạy lại được (seed/version/phần cứng/hash).
- [ ] **Bước 34 — Rà soát nhất quán số liệu, thuật ngữ.** → *mục tiêu:* không mâu thuẫn giữa thân bài, bảng, hình.
- [ ] **Bước 35 — Tự chấm lại bằng bộ thẩm định.** → *mục tiêu:* xác nhận bài đủ chuẩn trước khi nộp.
- [ ] **Bước 36 — Đưa lên Overleaf khi hoàn chỉnh.** → *mục tiêu:* bản sạch sẵn sàng nộp.
- [ ] **Bước 37 — Nộp IJIS.** → *mục tiêu:* hoàn tất.

**Mục tiêu cả Giai đoạn 5:** bản thảo đủ sức qua phản biện → nộp.

---

## Ba điểm dừng bắt buộc (nếu không đạt thì xem lại, chưa đi tiếp)
1. **Sau Bước 7:** mọi điều kiện tiên quyết đều đạt.
2. **Sau Bước 17:** kiểm tra rò rỉ cho kết quả thấp.
3. **Sau Bước 22:** cạnh taint đóng góp đủ; nếu không → báo kết quả phủ định, cân nhắc đổi hướng.
