"""Call graph mức file (tầng 3).

E_call: f -> g nếu một statement trong f gọi tên hàm g được định nghĩa trong CÙNG file
        (hàm thường theo tên; method theo tên ngắn '->m' khớp mọi 'Class::m' trong file — xấp xỉ).
E_include: mỗi mẫu là MỘT file độc lập nên include/require trỏ ra ngoài không resolve được -> rỗng.
        Số câu include vẫn được đếm (dump['n_includes']) và token 'include*' vẫn mang vai trò sink.
"""
from __future__ import annotations


def callee_index(names) -> dict[str, list[int]]:
    """Tên lời gọi -> chỉ số function. Hàm thường theo tên (lower); method 'Class::m' -> '->m'.
    functions[0] (<main>) không được gọi. Dùng chung cho E_call và bridge taint liên thủ tục."""
    by_name: dict[str, list[int]] = {}
    for k, name in enumerate(names):
        name = (name or "").lower()
        if k == 0 or not name:
            continue
        if "::" in name:
            by_name.setdefault("->" + name.split("::", 1)[1], []).append(k)
        else:
            by_name.setdefault(name, []).append(k)
    return by_name


def build_call_include(dump: dict) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    funcs = dump.get("functions") or []
    by_name = callee_index([fn.get("name") for fn in funcs])
    calls = set()
    for k, fn in enumerate(funcs):
        for st in fn.get("stmts", []):
            for c in st.get("calls", []):
                for g in by_name.get(c.lower(), ()):
                    if g != k:
                        calls.add((k, g))
    return sorted(calls), []
