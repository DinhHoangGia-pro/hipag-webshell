"""Seed source/sink/decode cho PHP — weak supervision cho Learned Taint-Dependency Predictor (RQF-06).

Dữ liệu tham chiếu + hàm phân loại nhẹ; KHÔNG phụ thuộc torch.
Mở rộng danh sách khi gặp biến thể mới (đây là seed, không phải bảng luật cứng đầy đủ).
"""
from __future__ import annotations

# Nguồn do người dùng kiểm soát (tainted sources)
SOURCES = [
    "$_GET", "$_POST", "$_REQUEST", "$_COOKIE", "$_FILES", "$_SERVER",
    "$_ENV", "$HTTP_RAW_POST_DATA", "php://input", "getenv", "apache_request_headers",
]

# Hàm nguy hiểm (sinks) — thực thi mã/lệnh hoặc nạp file
SINKS = [
    "eval", "assert", "system", "exec", "shell_exec", "passthru",
    "popen", "proc_open", "pcntl_exec",
    "preg_replace",            # /e modifier (PHP < 7)
    "create_function", "call_user_func", "call_user_func_array",
    "include", "include_once", "require", "require_once",
    "array_map", "array_filter", "usort",   # callback-based indirect sinks
]

# Hàm mã hoá/giải mã thường bọc payload (dấu hiệu obfuscation)
DECODERS = [
    "base64_decode", "gzinflate", "gzuncompress", "gzdecode",
    "str_rot13", "hex2bin", "convert_uudecode", "urldecode", "rawurldecode",
]

_SRC = {s.lstrip("$").lower() for s in SOURCES}
_SNK = {s.lower() for s in SINKS}
_DEC = {s.lower() for s in DECODERS}


def classify_token(name: str) -> str | None:
    """Trả 'source' | 'sink' | 'decode' | None cho tên hàm/biến.

    Không phân biệt hoa thường, bỏ tiền tố '$'. Dùng để gán vai trò nút khi dựng đồ thị
    và để sinh cặp giám sát yếu cho predictor.
    """
    if not name:
        return None
    key = name.strip().lstrip("$").lower()
    if key in _SRC:
        return "source"
    if key in _SNK:
        return "sink"
    if key in _DEC:
        return "decode"
    return None
