# HiPaG — Mục lục nguyên liệu dự án

Toàn bộ vật liệu cho dự án **HiPaG (phát hiện webshell PHP → IJIS)**.

## 1. Kế hoạch & checklist
- `CHECKLIST.md` — checklist thực thi theo Bước (0 → 37).
- `KE_HOACH_HOAN_THIEN.md` — kế hoạch hoàn thiện 4 tầng (T0→T3).

## 2. Phác thảo bài báo
- `docs/phac_thao_HiPaG_tiengviet.md` — phác thảo tiếng Việt (bản xuất từ Claude Doc).
- `paper/main.tex` — bộ khung bài báo tiếng Anh (paper skeleton; mọi số qua `paper/numbers.tex`).

## 3. Worth (demand + novelty) — đã đóng
- `docs/demand_evidence.md` — bằng chứng nhu cầu E1/E2/E3 (OWASP/CWE/ATT&CK, CVE, survey) + ref IJIS.
- `docs/related_work_scan.md` — quét prior-art + bảng delta vs GlareShell.

## 4. Thẩm định (audit)
- `docs/OMNI_RQ_AUDIT_v4_HiPaG_webshell.md` — audit gốc (Worth 40).
- `docs/OMNI_RQ_AUDIT_v4_HiPaG_RETEST_postT0.md` — tái thẩm sau T0 (Worth 51).

## 5. Bộ khung code HiPaG
- `README.md`, `requirements.txt`, `.gitignore`, `configs/`, `scripts/`, `src/hipag/`,
  `experiments/`, `data/` (gitignored), `tools/`, `paper/`.
- Code Python đều là VỎ (signature + TODO) để điền dần.

## 6. Thiết lập
- `docs/SETUP_PHP.md` — cài PHP parser.
- `NGU_CANH.md` — ghi chú bàn giao ngữ cảnh (git-excluded khi làm thật).

## 7. Tài liệu tham khảo (references/)
- `references/SOURCES.md` — danh mục đầy đủ: đối thủ/baseline, obfuscation-evasion, demand/chuẩn/CVE, nền kỹ thuật, ref IJIS, công trình nhóm.
- `references/DOWNLOAD_LIST.txt` — danh sách URL để `wget -i` tải PDF trên máy (PDF không tải được từ môi trường cloud này).

## Ghi chú xuất xứ (đã làm sạch 06/11)
- Mọi tài liệu trong `references/SOURCES.md` chỉ ghi thứ **thấy trực tiếp khi tra** (tiêu đề + link; DOI/venue khi xuất hiện nguyên văn). Năm/DOI không xác minh được đã **xóa**.
- Ref nền (GATv2, UniMP, SEAL, RIPS, Pixy) để ở mục F — **chưa tra phiên này, phải tự xác minh** trước khi trích.
- Mốc "21/10/2026" **không có nguồn** đã gỡ khỏi phác thảo và kế hoạch. Bản audit gốc vẫn nhắc mốc này nhưng chỉ để **ghi nhận nó không nguồn** (một điểm yếu W1 cần sửa), không phải khẳng định.
- Số dataset (Tennc/JohnTroony/WebSHArk/Cycle183/MWF) là **do anh cung cấp**; cần đối chiếu lại khi thu thập thực tế.
