"""Đặc trưng nút: loại AST/statement + cờ source/sink/decode + entropy cục bộ + positional.

Cũng chứa: băm token -> id (đầu vào tier-1) và đặc trưng toàn cục mức file.
Không phụ thuộc torch (dùng được trong pipeline dựng đồ thị).
"""
from __future__ import annotations

import math
import re
import zlib
from collections import Counter

from .taint_seeds import DECODERS, stmt_roles

# Loại statement (tên nút nikic/PHP-Parser đã bỏ tiền tố Stmt_/Expr_). Ngoài danh sách -> 'Other'.
STMT_KINDS = [
    "Expression", "Assign", "Echo", "If", "ElseIf", "Else", "While", "Do", "For", "Foreach",
    "Switch", "Return", "FuncCall", "MethodCall", "StaticCall", "Include", "Eval", "Global",
    "Unset", "Try", "Function", "ClassMethod", "InlineHTML", "Nop", "Other",
]
_KIND_IDX = {k: i for i, k in enumerate(STMT_KINDS)}
ROLE_NAMES = ["source", "sink", "decode"]
# Cờ 'direct_source_sink': statement chứa CẢ source lẫn sink (vd `eval($_POST['c'])`).
# primary_role coi nút này là sink nên nó KHÔNG sinh cặp source->sink (i != j) -> cờ này giữ lại tín hiệu
# taint trực tiếp trong-statement cho mô hình.
# TODO(RQF-06): quy ước tạm thời — cân nhắc tách nút biểu thức (sink-arg) để có cặp positive thật.
N_FLAGS = 1
N_NUMERIC = 3   # entropy, độ dài, vị trí tương đối
NODE_FEAT_DIM = len(STMT_KINDS) + len(ROLE_NAMES) + N_FLAGS + N_NUMERIC

GLOBAL_FEATURES = ["shannon_entropy", "has_eval", "has_decode", "has_var_func"]
GLOBAL_FEAT_DIM = len(GLOBAL_FEATURES)


def shannon_entropy(s: str) -> float:
    """Entropy Shannon theo ký tự (bit/ký tự). Chuỗi rỗng -> 0."""
    if not s:
        return 0.0
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def kind_index(kind: str) -> int:
    k = re.sub(r"^(Stmt|Expr)_", "", kind or "")
    return _KIND_IDX.get(k, _KIND_IDX["Other"])


def node_vector(node: dict, pos: int = 0, n_in_func: int = 1) -> list[float]:
    """node = {'kind', 'text', 'tokens', 'calls', 'callargs', 'constructs'} (statement IR; sink theo call node).
    Trả [one-hot kind | cờ source,sink,decode | direct_source_sink | entropy/8, log1p(len)/8, vị trí tương đối]."""
    v = [0.0] * NODE_FEAT_DIM
    v[kind_index(node.get("kind", ""))] = 1.0
    roles = stmt_roles(node)                     # luật call node: cần calls/callargs/constructs của statement
    off = len(STMT_KINDS)
    for r_i, r in enumerate(ROLE_NAMES):
        if r in roles:
            v[off + r_i] = 1.0
    off += len(ROLE_NAMES)
    v[off] = float("source" in roles and "sink" in roles)          # direct_source_sink
    off += N_FLAGS
    text = node.get("text", "")
    v[off] = shannon_entropy(text) / 8.0
    v[off + 1] = math.log1p(len(text)) / 8.0
    v[off + 2] = pos / max(n_in_func - 1, 1)
    return v


def token_ids(tokens, vocab_size: int, max_len: int) -> list[int]:
    """Băm token -> id ∈ [1, vocab_size) (0 = PAD), cắt/đệm về max_len. crc32 để ổn định giữa các tiến trình."""
    ids = [1 + zlib.crc32(t.lower().encode("utf-8", "replace")) % (vocab_size - 1) for t in tokens[:max_len]]
    return ids + [0] * (max_len - len(ids))


_RE_EVAL = re.compile(r"\b(eval|assert)\s*\(", re.I)
_RE_DEC = re.compile(r"\b(" + "|".join(map(re.escape, DECODERS)) + r")\s*\(", re.I)
_RE_VARFUNC = re.compile(r"\$\w+\s*\(")


def global_features(source_text: str) -> list[float]:
    """[entropy/8, has_eval, has_decode, has_var_func] mức file (thứ tự = GLOBAL_FEATURES)."""
    t = source_text or ""
    return [
        shannon_entropy(t) / 8.0,
        float(bool(_RE_EVAL.search(t))),
        float(bool(_RE_DEC.search(t))),
        float(bool(_RE_VARFUNC.search(t))),
    ]
