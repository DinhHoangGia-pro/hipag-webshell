# CLAUDE.md — ngữ cảnh dự án HiPaG (cho Claude Code / Copilot)

## Dự án
HiPaG — Hierarchical Program-Graph Transformer with Learned Taint Dependencies cho **phát hiện webshell PHP**,
nhắm tạp chí **IJIS (Springer 10207)**. Xem `INDEX.md`, `CHECKLIST.md`, `docs/`.

## MÔI TRƯỜNG PYTHON (quan trọng)
- Virtualenv: **`/home/dhgia/Work/WorkingD/WORK/Research/2027/hipag_venv`**
- Kích hoạt trước mọi lệnh Python:
  ```bash
  source /home/dhgia/Work/WorkingD/WORK/Research/2027/hipag_venv/bin/activate
  ```
- Hệ thống chỉ có `python3` (Python 3.14, externally-managed/PEP 668). **KHÔNG** `pip install` ngoài venv
  (sẽ lỗi externally-managed). Trong venv thì `python`/`pip` dùng bình thường.
- Nếu `torch`/`torch-geometric` không cài được trên 3.14 → tạo lại venv bằng `python3.12 -m venv`.

## VỊ TRÍ
- Repo: `/home/dhgia/Work/WorkingD/WORK/Research/2027/hipag-webshell`
- **Không** tạo file/thư mục trong `~`. Mọi thứ nằm trên ổ WorkingD.
- PHP parser: `composer require nikic/php-parser` chạy **trong repo** (dùng cho `tools/php/dump_ast.php`);
  `vendor/` không lên git.

## QUY ƯỚC (bắt buộc tuân theo)
- **Paper KHÔNG lên git.** `paper/` đã gitignore; bản thảo ở local + Overleaf khi hoàn chỉnh.
  `main.tex` là bản mới nhất, sao lưu `main_v[N].tex` trước khi sửa lớn. **Không** thêm bước git-commit cho paper.
- `data/` không bao giờ lên git.
- Mọi số trong paper lấy qua `paper/numbers.tex` (eval.py ghi ra) — không gõ tay số vào thân bài.
- Mọi bảng kết quả: **≥5 seed**, báo mean±sd + base-rate precision {10%,1%,0.1%}.
- **Không** đo/log/nhắc nhiệt độ máy trong mọi job dài.

## TRẠNG THÁI HIỆN TẠI
- Pre-code (Worth) xong: demand + novelty + tiêu đề (xem `CHECKLIST.md` Bước 1–3).
- **Bước kế tiếp: Bước 5 — well-pose Taint-Dependency Predictor** (`src/hipag/model/taint_predictor.py`,
  `src/hipag/graph/taint_seeds.py`).
- Code Python hiện là **vỏ** (signature + `TODO(RQF-xx)`); điền dần theo CHECKLIST.

## CÁCH CHẠY (sau khi có data/)
```bash
python scripts/dataset/01_collect_webshells.py --config configs/dataset/collect.yaml
# ... 02..06 theo thứ tự (xem README.md) ...
python scripts/metadata_probe.py   --config configs/experiment/rq1_detection.yaml
python scripts/run_experiment.py   --config configs/experiment/rq4_ablation.yaml --seeds 5
```
