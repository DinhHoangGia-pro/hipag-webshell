"""CFG + DFG trong hàm.

CFG: dựng sẵn bên PHP (tools/php/dump_ast.php) theo cấu trúc if/loop/switch/try/break/continue/return — xấp xỉ,
     không có cạnh exception/goto.
DFG: reaching-definitions trên CFG: cạnh d -> u nếu biến v được định nghĩa ở d, dùng ở u, và định nghĩa
     d còn "sống" tới u. Gán phần tử mảng/thuộc tính ($a[k] = ...) tính là định nghĩa $a (không kill
     chính xác — xấp xỉ bảo thủ).
"""
from __future__ import annotations

from collections import deque


def build_cfg(fn: dict) -> list[tuple[int, int]]:
    n = len(fn.get("stmts", []))
    return [(int(i), int(j)) for i, j in fn.get("cfg", []) if 0 <= i < n and 0 <= j < n and i != j]


def build_dfg(stmts: list[dict], cfg: list[tuple[int, int]]) -> list[tuple[int, int]]:
    n = len(stmts)
    if n == 0:
        return []
    succ: list[list[int]] = [[] for _ in range(n)]
    pred: list[list[int]] = [[] for _ in range(n)]
    for i, j in cfg:
        succ[i].append(j); pred[j].append(i)
    defs = [set(s.get("defs", [])) for s in stmts]
    uses = [set(s.get("uses", [])) for s in stmts]

    # IN/OUT: dict var -> frozenset(def node)
    out: list[dict] = [{} for _ in range(n)]
    inn: list[dict] = [{} for _ in range(n)]
    work = deque(range(n)); queued = [True] * n
    while work:
        u = work.popleft(); queued[u] = False
        merged: dict = {}
        for p in pred[u]:
            for v, ds in out[p].items():
                merged[v] = merged.get(v, frozenset()) | ds
        inn[u] = merged
        new = dict(merged)
        for v in defs[u]:
            new[v] = frozenset((u,))
        if new != out[u]:
            out[u] = new
            for s in succ[u]:
                if not queued[s]:
                    queued[s] = True; work.append(s)
    edges = set()
    for u in range(n):
        for v in uses[u]:
            for d in inn[u].get(v, ()):
                if d != u:
                    edges.add((d, u))
    return sorted(edges)
