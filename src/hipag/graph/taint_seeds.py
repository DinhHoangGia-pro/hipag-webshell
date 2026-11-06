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


def token_roles(tokens) -> set[str]:
    """Tập vai trò {'source','sink','decode'} xuất hiện trong danh sách token của một nút."""
    out = set()
    for t in tokens:
        r = classify_token(t)
        if r is not None:
            out.add(r)
    return out


def primary_role(tokens) -> str | None:
    """Vai trò chính của một nút statement để sinh cặp giám sát yếu.

    Ưu tiên sink > source > decode: statement kiểu `eval($_GET['x'])` được coi là SINK
    (nó là nơi tiêu thụ taint). Hệ quả: cặp source->sink trong CÙNG một statement không
    sinh positive (i != j); thông tin đó vẫn có trong cờ vai trò multi-hot của đặc trưng nút.
    TODO(RQF-06): chốt quy ước này trong Bước 5 (self-pair hay tách nút biểu thức).
    """
    roles = token_roles(tokens)
    for r in ("sink", "source", "decode"):
        if r in roles:
            return r
    return None


def reachable_within(edges, num_nodes: int, max_hops: int):
    """Trả callable reachable(i, j): True nếu j tới được từ i trong ≤ max_hops bước
    theo `edges` (iterable (u, v) có hướng — thường là CFG ∪ DFG ∪ E_seq trong hàm).
    BFS lười + cache theo nút nguồn. i == j trả False (không xét self-loop)."""
    adj: list[list[int]] = [[] for _ in range(num_nodes)]
    for u, v in edges:
        adj[u].append(v)
    cache: dict[int, set[int]] = {}

    def reach_set(i: int) -> set[int]:
        if i not in cache:
            seen, frontier = {i}, [i]
            for _ in range(max_hops):
                nxt = []
                for u in frontier:
                    for v in adj[u]:
                        if v not in seen:
                            seen.add(v); nxt.append(v)
                if not nxt:
                    break
                frontier = nxt
            seen.discard(i)
            cache[i] = seen
        return cache[i]

    def reachable(i: int, j: int) -> bool:
        return i != j and j in reach_set(i)

    reachable.reach_set = reach_set   # dùng để liệt kê cặp ứng viên
    return reachable
