"""Seed source/sink/decode cho PHP — weak supervision cho Learned Taint-Dependency Predictor (RQF-06).

Nguyên tắc: NHÃN CHẶT + ỨNG VIÊN NỚI.
  RULE_SINKS      — CHẶT, chỉ dùng sinh NHÃN positive (sem_pos). Vai trò 'sink'.
  CANDIDATE_SINKS — NỚI = RULE_SINKS ∪ CANDIDATE_EXTRA, chỉ dùng HÌNH THÀNH cặp ứng viên E_sem (cand),
                    KHÔNG làm nhãn. Sink chỉ-ứng-viên có vai trò 'cand_sink'.
Một số sink phụ thuộc NGỮ CẢNH statement (token_roles quyết định, classify_token trả 'cond_sink'):
  include/require(_once) : rule chỉ khi đối số ĐỘNG (có biến / <dyncall> / chuỗi nội suy); tĩnh -> không phải sink
  preg_replace           : rule chỉ khi thấy literal pattern có modifier /e; không -> không phải sink
  fopen                  : ứng viên khi chế độ ghi (w/a/x/c/+) hoặc không thấy chế độ; 'r'/'rb' -> không phải sink
LUẬT CALL NODE (một luật cho MỌI sink): token tên-sink chỉ là sink khi tên đó là CALL NODE thật của statement —
callee của FuncCall/MethodCall (calls/callargs; gọi động -> '<dyncall>') hoặc construct eval/include/require/
backtick (constructs) — do tools/php/dump_ast.php xuất từ AST (call_nodes_of). Literal chuỗi / identifier
trùng tên sink ($f = 'assert', echo 'eval') KHÔNG là sink. Không có thông tin call node -> không có sink.
Mọi danh sách ở ĐÂY (một nguồn). KHÔNG phụ thuộc torch.
"""
from __future__ import annotations

import re

# Nguồn do người dùng kiểm soát (tainted sources).
# file_get_contents('php://input') được bắt qua literal token 'php://input' (dump_ast.php giữ literal ≤32 ký tự).
SOURCES = [
    "$_GET", "$_POST", "$_REQUEST", "$_COOKIE", "$_SERVER", "$_FILES", "$_SESSION", "$_ENV",
    "$HTTP_RAW_POST_DATA", "php://input", "getenv", "apache_request_headers",
    # mảng input kiểu cũ (PHP < 5.4, register_long_arrays).
    # KHÔNG có $GLOBALS: là bảng ký hiệu toàn cục/alias, không phải input ngoài.
    "$HTTP_POST_VARS", "$HTTP_GET_VARS", "$HTTP_COOKIE_VARS", "$HTTP_REQUEST_VARS",
]

# Sink CHẶT không phụ thuộc ngữ cảnh. Backtick `...` được dump_ast.php phát thành token 'shell_exec';
# gọi hàm qua biến $f(...) / $o->$m(...) phát thành '<dyncall>'.
RULE_SINKS = [
    "eval", "assert", "system", "exec", "shell_exec", "passthru", "popen", "proc_open", "pcntl_exec",
    "create_function", "call_user_func", "call_user_func_array", "<dyncall>",
    "unserialize",            # object injection -> RCE; CHỈ tính khi là call node thật (xem CALL_ONLY)
]
# Sink CHẶT có điều kiện ngữ cảnh (xem token_roles).
RULE_SINKS_CONDITIONAL = ["preg_replace", "include", "include_once", "require", "require_once"]
# Sink chỉ-ứng-viên (NỚI): ghi file / mạng / đọc file — KHÔNG làm nhãn.
CANDIDATE_EXTRA = ["fwrite", "fputs", "file_put_contents", "move_uploaded_file", "copy", "readfile",
                   "fsockopen", "mail"]
CANDIDATE_CONDITIONAL = ["fopen"]          # chỉ khi chế độ ghi
# extract: variable injection. ỨNG VIÊN; thành sink CHẶT khi đối số chứa mảng source (extract($_POST)).
#          Không mô hình "spreader" (biến do extract sinh ra không được coi là nhiễm) — chỉ cạnh source->extract.
CANDIDATE_EXTRACT = ["extract"]
# Họ callback: ứng viên khi callback là callable BIẾN (ob_start($cb)); literal ('ob_gzhandler') / rỗng -> không.
CANDIDATE_CALLBACK = ["ob_start"]
CANDIDATE_SINKS = (RULE_SINKS + RULE_SINKS_CONDITIONAL + CANDIDATE_EXTRA + CANDIDATE_CONDITIONAL
                   + CANDIDATE_EXTRACT + CANDIDATE_CALLBACK)
# Sink có điều kiện chỉ theo đối số (luật call node áp cho MỌI sink, xem call_nodes_of).
CALL_ONLY = {"unserialize", "extract", "ob_start"}
# Construct ngôn ngữ là sink (dump_ast.php xuất trong 'constructs'; không có '(').
CONSTRUCT_SINKS = {"eval", "include", "include_once", "require", "require_once", "shell_exec"}
SINKS = RULE_SINKS                          # tên cũ (tương thích): = sink CHẶT không điều kiện

# Hàm mã hoá/giải mã thường bọc payload (dấu hiệu obfuscation)
DECODERS = [
    "base64_decode", "gzinflate", "gzuncompress", "gzdecode",
    "str_rot13", "hex2bin", "convert_uudecode", "urldecode", "rawurldecode",
]

_SRC = {s.lstrip("$").lower() for s in SOURCES}
_RULE = {s.lower() for s in RULE_SINKS}
_COND = {s.lower() for s in RULE_SINKS_CONDITIONAL + CANDIDATE_CONDITIONAL} | CALL_ONLY
_CAND = {s.lower() for s in CANDIDATE_EXTRA}
_DEC = {s.lower() for s in DECODERS}
_INCLUDES = {"include", "include_once", "require", "require_once"}
_FOPEN_MODE = re.compile(r"^[rwaxc][bt+]{0,3}$")
_PAIRED = {"(": ")", "{": "}", "[": "]", "<": ">"}


def classify_token(name: str) -> str | None:
    """Loại của MỘT token (không ngữ cảnh):
    'source' | 'sink' (RULE, không điều kiện) | 'cond_sink' (cần ngữ cảnh statement — dùng token_roles)
    | 'cand_sink' (chỉ ứng viên) | 'decode' | None. Không phân biệt hoa thường, bỏ tiền tố '$'."""
    if not name:
        return None
    key = name.strip().lstrip("$").lower()
    if key in _SRC:
        return "source"
    if key in _COND:                         # cần ngữ cảnh statement (kể cả CALL_ONLY như unserialize)
        return "cond_sink"
    if key in _RULE:
        return "sink"
    if key in _CAND:
        return "cand_sink"
    if key in _DEC:
        return "decode"
    return None


def has_e_modifier(lit: str) -> bool:
    """Literal regex có modifier /e (vd '/x/e', '#a#ie', '{x}e')."""
    if not lit or len(lit) < 3 or lit[0].isalnum() or lit[0].isspace() or lit[0] == "\\":
        return False
    close = _PAIRED.get(lit[0], lit[0])
    k = lit.rfind(close)
    if k <= 0:
        return False
    mods = lit[k + 1:]
    return mods.isalpha() and "e" in mods


def _is_dynamic(args) -> bool:
    return any(t.startswith("$") or t in ("<dyncall>", "<istr>") for t in args)


def call_nodes_of(stmt: dict) -> frozenset:
    """CALL NODE thật của một statement (từ AST dump): callee (calls + tên trong callargs, gọi động '<dyncall>')
    ∪ construct (eval/include/require/backtick). Đây cũng là nguồn mà bridge liên thủ tục dùng."""
    out = {str(c).lower() for c in stmt.get("calls") or []}
    out |= {str(ca.get("name") or "").lower() for ca in stmt.get("callargs") or []}
    out |= {str(c).lower() for c in stmt.get("constructs") or []}
    out.discard("")
    return frozenset(out)


def _cond_role(name: str, i: int, tokens) -> str | None:
    """Giải sink có điều kiện tại vị trí i của statement -> 'sink' | 'cand_sink' | None.
    (Đã qua luật call node ở token_roles.)"""
    if name in CALL_ONLY:
        args = tokens[i + 1:]
        if name == "unserialize":
            return "sink"
        if name == "extract":
            return "sink" if any(t.startswith("$") and classify_token(t) == "source" for t in args) else "cand_sink"
        return "cand_sink" if any(t.startswith("$") for t in args) else None      # ob_start($cb)
    if name in _INCLUDES:
        return "sink" if _is_dynamic(tokens[i + 1:]) else None
    if name == "preg_replace":
        return "sink" if any(not t.startswith("$") and has_e_modifier(t) for t in tokens) else None
    if name == "fopen":
        modes = [t for t in tokens[i + 1:] if _FOPEN_MODE.match(t)]
        if not modes:
            return "cand_sink"                    # không thấy chế độ (biến) -> NỚI: vẫn là ứng viên
        return "cand_sink" if any(c in m for m in modes for c in "waxc+") else None
    return None


def token_roles(tokens, call_nodes=frozenset()) -> set[str]:
    """Vai trò của MỘT statement theo ngữ cảnh: tập con {'source','sink','cand_sink','decode'}.
    'sink' = sink CHẶT (đủ làm nhãn); 'cand_sink' = sink chỉ-ứng-viên. Sink chặt cũng là ứng viên
    (xem is_candidate_sink). call_nodes: tập call node thật (call_nodes_of) — token tên-sink KHÔNG nằm
    trong đó (literal/identifier) thì không là sink. Có dict statement -> dùng stmt_roles."""
    tokens = list(tokens)
    out = set()
    for i, t in enumerate(tokens):
        r = classify_token(t)
        if r in ("sink", "cond_sink", "cand_sink") and t.strip().lower() not in call_nodes:
            continue
        if r == "cond_sink":
            r = _cond_role(t.strip().lower(), i, tokens)
        if r is not None:
            out.add(r)
    if "sink" in out:
        out.discard("cand_sink")
    return out


def is_candidate_sink(roles) -> bool:
    return "sink" in roles or "cand_sink" in roles


def stmt_roles(stmt: dict) -> set[str]:
    """token_roles với call node lấy từ AST dump của statement."""
    return token_roles(stmt.get("tokens", []), call_nodes_of(stmt))


def primary_role(tokens, call_nodes=frozenset()) -> str | None:
    """Vai trò chính của một nút statement để sinh cặp giám sát yếu.

    Ưu tiên sink > source > cand_sink > decode: statement kiểu `eval($_GET['x'])` được coi là SINK
    (nó là nơi tiêu thụ taint). Hệ quả: cặp source->sink trong CÙNG một statement không
    sinh positive (i != j); thông tin đó vẫn có trong cờ vai trò multi-hot của đặc trưng nút.
    TODO(RQF-06): chốt quy ước này trong Bước 5 (self-pair hay tách nút biểu thức).
    """
    roles = token_roles(tokens, call_nodes)
    for r in ("sink", "source", "cand_sink", "decode"):
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
