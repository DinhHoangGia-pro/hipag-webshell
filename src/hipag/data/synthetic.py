"""Dữ liệu GIẢ cho smoke-test pipeline (KHÔNG dùng cho bất kỳ con số nào trong paper).

Sinh IR ngẫu nhiên rồi đi qua đúng `build_hetero_from_ir` như dữ liệu thật:
  - webshell (y=1): luồng source -> (decode) -> sink nối bằng cạnh DFG, đôi khi cùng statement.
  - benign  (y=0): code thường; có mẫu "hard benign" dùng call_user_func / $_GET + htmlspecialchars
    (có sink hoặc source nhưng KHÔNG có luồng source->sink).
"""
from __future__ import annotations

import random

from ..graph.hierarchical_graph import build_hetero_from_ir

_BENIGN_TOK = ["$a", "$b", "$row", "$i", "=", "(", ")", ";", "strlen", "echo", "return", "foreach",
               "array_push", "htmlspecialchars", "mysqli_query", "count", "implode", "trim", "'ok'", "+"]
_KINDS = ["Expression", "Assign", "Echo", "If", "Return", "FuncCall", "Foreach"]


def _stmt(rng, kind=None, extra=(), calls=(), constructs=()):
    """Statement giả theo đúng định dạng dump_ast.php: token + call node thật (calls/constructs).
    Token nền (_BENIGN_TOK) không phải call node -> 'strlen' hay 'echo' trong đó KHÔNG là lời gọi."""
    toks = [rng.choice(_BENIGN_TOK) for _ in range(rng.randint(2, 8))]
    rng.shuffle(toks)
    k = rng.randint(0, len(toks))
    toks[k:k] = list(extra)          # giữ thứ tự extra
    return {"kind": kind or rng.choice(_KINDS), "text": " ".join(toks), "tokens": toks,
            "calls": list(calls), "constructs": list(constructs)}


def _sink_stmt(rng, sink):
    """eval là construct (dump_ast.php phát 'eval' KHÔNG kèm '('); hàm khác là FuncCall: tên + '('."""
    if sink == "eval":
        return _stmt(rng, "Eval", ["eval", "$x"], constructs=["eval"])
    return _stmt(rng, "FuncCall", [sink, "(", "$x"], calls=[sink])


def make_synthetic_ir(rng: random.Random, label: int) -> dict:
    funcs = []
    for f in range(rng.randint(1, 4)):
        n = rng.randint(3, 12)
        stmts = [_stmt(rng) for _ in range(n)]
        cfg = [(i, i + 1) for i in range(n - 1)]
        if n > 4 and rng.random() < 0.5:                         # một nhánh if
            cfg.append((1, rng.randint(3, n - 1)))
        dfg = [(i, rng.randint(i + 1, n - 1)) for i in range(n - 1) if rng.random() < 0.3]
        funcs.append({"name": f"f{f}", "stmts": stmts, "cfg": cfg, "dfg": dfg})

    target = rng.choice(funcs)
    st, n = target["stmts"], len(target["stmts"])
    if label == 1:
        if rng.random() < 0.25:                                   # eval($_POST['c']) một statement
            k = rng.randrange(n)
            st[k] = _stmt(rng, "Eval", ["eval", "$_POST", "c"], constructs=["eval"])
        else:
            i = rng.randrange(0, n - 2)
            j = rng.randint(i + 2, n - 1)
            src = rng.choice(["$_POST", "$_GET", "$_REQUEST", "$_COOKIE"])
            sink = rng.choice(["eval", "assert", "system", "shell_exec", "create_function"])
            st[i] = _stmt(rng, "Assign", ["$x", "=", src])
            st[j] = _sink_stmt(rng, sink)
            if rng.random() < 0.6:                                # bọc decode ở giữa
                m = rng.randint(i + 1, j - 1)
                dec = rng.choice(["base64_decode", "gzinflate", "str_rot13"])
                st[m] = _stmt(rng, "Assign", ["$x", "=", dec, "(", "$x"], calls=[dec])
                target["dfg"] += [(i, m), (m, j)]
            else:
                target["dfg"].append((i, j))
    else:
        r = rng.random()
        if r < 0.3:                                               # hard benign: callback hợp lệ
            st[rng.randrange(n)] = _stmt(rng, "FuncCall", ["call_user_func", "(", "$cb"], calls=["call_user_func"])
        elif r < 0.6:                                             # đọc input nhưng escape, không có sink
            st[rng.randrange(n)] = _stmt(rng, "Echo", ["echo", "htmlspecialchars", "(", "$_GET"], calls=["htmlspecialchars"])

    F = len(funcs)
    calls = [(0, k) for k in range(1, F) if rng.random() < 0.7]
    text = "<?php\n" + "\n".join(s["text"] for fn in funcs for s in fn["stmts"])
    return {"functions": funcs, "calls": calls, "includes": [], "source_text": text}


def make_synthetic_dataset(n: int, seed: int = 0, pos_ratio: float = 0.5, graph_cfg: dict | None = None):
    """Danh sách n HeteroData giả có nhãn y."""
    rng = random.Random(seed)
    out = []
    for k in range(n):
        y = int(rng.random() < pos_ratio)
        ir = make_synthetic_ir(rng, y)
        out.append(build_hetero_from_ir(ir, graph_cfg, label=y, seed=seed * 100003 + k))
    return out
