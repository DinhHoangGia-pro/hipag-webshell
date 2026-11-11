#!/usr/bin/env python3
"""Đo độ phủ cặp E_sem trên đồ thị ĐÃ DỰNG (chỉ đọc — KHÔNG rebuild 04, KHÔNG sửa builder).

Nguồn chân lý cho (a)–(f) là chính file .pt trong data/features_small:
  - cờ vai trò multi-hot của statement (cột source/sink/decode/direct_source_sink trong stmt.x),
  - cặp luật đã lưu (stmt-sem_pos-stmt), cặp ứng viên (stmt-cand-stmt), n_cand_full / cand_capped,
  - cạnh seq/cfg/dfg, stmt->func, func-call-func.
Token gốc KHÔNG được lưu trong .pt (x_tok là id băm). Để đo seed-miss (iv) và phần mất do cắt, script chạy lại
tools/php/dump_ast.php ở chế độ chỉ đọc (kết quả giữ trong RAM), áp đúng cap max_func_per_file/max_stmt_per_block
của builder, rồi KIỂM CHỨNG căn khớp từng statement: cờ vai trò tính lại từ token phải trùng cờ trong .pt
(cột align_ok). File không khớp -> các cột dựa trên token để trống, không suy đoán.

Định nghĩa (theo file, tách benign/webshell):
  (a) có ≥1 statement cờ source   (b) có ≥1 cờ sink   (c) cả hai
  (d) trong (c): có ≥1 cặp luật (sem_pos)    [+ số còn trong tập ứng viên = cạnh rule_e_sem/warmup thực dùng]
  (e) trong (c): có ≥1 statement direct_source_sink=1
  (f) trong (c): không (d) và không (e)
Nguyên nhân (f) — i/ii/same_fn LOẠI TRỪ nhau; iii/iv là cờ CHỒNG LẤN; mechanism giải thích cơ chế thật:
  i   global : mọi hàm chứa CẢ source lẫn sink đều là <main> (phạm vi file)
  ii  cross  : không hàm nào chứa cả hai (source/sink ở khác hàm); call_connected = có đường E_call nối
  same_fn    : có hàm thường (không phải <main>) chứa cả hai
  mechanism (khi cùng hàm): beyond_hops = có đường seq∪cfg∪dfg nhưng > max_hops;
                            no_forward_path = không có đường (sink đứng trước source, không có back-edge)
  iii via_decoder : có chuỗi DFG source -> ... -> decoder -> ... -> sink
  iv  seed_miss   : trong cửa sổ ≤ max_hops của source có statement chứa token GIỐNG sink (hoặc ngược lại)
                    mà không có trong SOURCES/SINKS/DECODERS — tức mở rộng seed thì đã có cặp.

Chạy:
  python scripts/analysis/esem_coverage.py                 # đầy đủ (dump PHP lại, ~vài phút)
  python scripts/analysis/esem_coverage.py --no-php        # chỉ đồ thị (bỏ iv + phần mất do cắt)
  python scripts/analysis/esem_coverage.py --limit 200     # thử nhanh
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from collections import Counter, deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hipag.graph.node_features import STMT_KINDS  # noqa: E402
from hipag.graph.taint_seeds import SINKS, call_nodes_of, classify_token, token_roles  # noqa: E402
from hipag.utils.config import load_config  # noqa: E402

COL_SRC = len(STMT_KINDS)
COL_SINK, COL_DEC, COL_DIRECT = COL_SRC + 1, COL_SRC + 2, COL_SRC + 3

# ---- token "giống" sink/source nhưng KHÔNG có trong seed (đã chuẩn hoá: lower, bỏ '$', bỏ '->') ----
SINK_LIKE = {
    # callback / gọi gián tiếp
    "array_walk", "array_walk_recursive", "array_reduce", "uasort", "uksort", "register_shutdown_function",
    "register_tick_function", "ob_start", "iterator_apply", "forward_static_call", "forward_static_call_array",
    "preg_replace_callback", "preg_replace_callback_array", "mb_ereg_replace", "mb_eregi_replace",
    "header_register_callback",
    "invoke", "invokeargs", "newinstance", "newinstanceargs",
    # ghi file / mạng / thực thi khác
    "file_put_contents", "fwrite", "fputs", "move_uploaded_file", "copy", "mail", "curl_exec",
    "fsockopen", "pfsockopen", "unserialize", "extract", "parse_str", "putenv", "dl",
    "highlight_file", "show_source", "readfile",
}
# (SINK_LIKE chỉ khớp khi token là LỜI GỌI: tên hàm có token '(' ngay sau — dump_ast.php luôn phát '(' sau
#  tên FuncCall — hoặc method '->x'. Biến '$dl' hay literal 'Copy' KHÔNG tính.)
SOURCE_VARS_LIKE = {"$_session", "$globals", "$argv", "$http_get_vars", "$http_post_vars", "$http_cookie_vars",
                    "$http_post_files", "$http_server_vars"}
SOURCE_CALLS_LIKE = {"getallheaders", "stream_get_contents"}
_SEED_CALL_RE = re.compile(r"(?<![\w$])(" + "|".join(
    sorted({re.escape(s.lower()) for s in SINKS}, key=len, reverse=True)) + r")\s*\(")
_SEED_SRC_RE = re.compile(r"\$_(get|post|request|cookie|files|server|env)\b|\$http_raw_post_data|php://input"
                          r"|(?<![\w$])(getenv|apache_request_headers)\s*\(")


def suspect(tok: str, is_call: bool) -> tuple[str, str] | None:
    """Token không phải seed nhưng giống source/sink -> (vai trò, loại); None nếu không.
    is_call: token là tên hàm được gọi (theo sau là '(') hoặc method '->x'."""
    if not tok or classify_token(tok) is not None:
        return None
    t = tok.strip().lower()
    if t == "<dyncall>":
        return "sink", "dyncall"
    if t.startswith("->"):
        t, is_call = t[2:], True
    if is_call and t in SINK_LIKE:
        return "sink", "unseeded_name"
    if (is_call and t in SOURCE_CALLS_LIKE) or (tok.startswith("$") and t in SOURCE_VARS_LIKE):
        return "source", "unseeded_name"
    if not is_call and not tok.startswith("$"):        # literal chuỗi chứa "eval(" / "$_POST" ...
        if _SEED_CALL_RE.search(t):
            return "sink", "seed_in_literal"
        if _SEED_SRC_RE.search(t):
            return "source", "seed_in_literal"
    return None


def has_sink_name(tokens: list[str]) -> bool:
    """Statement có token TRÙNG TÊN sink (kể cả literal) — so với cờ sink (luật call node) để đếm literal bị loại."""
    return any(classify_token(t) in ("sink", "cond_sink") for t in tokens)


def stmt_suspects(tokens: list[str], text: str, cn=frozenset()) -> list[tuple[str, str, str]]:
    """[(vai trò, loại, token)] cho một statement. Thêm 'text_only': seed có trong text nhưng không thành token
    (bị cắt MAX_TOK=64 hoặc nằm trong literal >32 ký tự -> <str>/<longstr>)."""
    out = []
    for i, t in enumerate(tokens):
        s = suspect(t, t.strip().lower() in cn)             # luật call node (AST dump), không heuristic '(' 
        if s:
            out.append((s[0], s[1], t))
    roles = token_roles(tokens, cn)
    low = (text or "").lower()
    if "sink" not in roles and _SEED_CALL_RE.search(low):
        out.append(("sink", "text_only", _SEED_CALL_RE.search(low).group(1)))
    if "source" not in roles and _SEED_SRC_RE.search(low):
        out.append(("source", "text_only", _SEED_SRC_RE.search(low).group(0)))
    return out


# --------------------------------------------------------------------------------------------- đồ thị
def _bfs(adj, starts, max_hops=None) -> dict[int, int]:
    dist = {s: 0 for s in starts}
    q = deque(starts)
    while q:
        u = q.popleft()
        if max_hops is not None and dist[u] >= max_hops:
            continue
        for v in adj[u]:
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


def _adj(n, *edge_lists, reverse=False):
    adj = [[] for _ in range(n)]
    for el in edge_lists:
        for u, v in el:
            if reverse:
                u, v = v, u
            adj[u].append(v)
    return adj


def _flat_stmts(dump: dict, max_func: int, max_s: int, cap: bool = True):
    """Danh sách (tokens, text, call_nodes) theo ĐÚNG thứ tự nút stmt của builder (build_hetero_from_ir)."""
    funcs = list(dump.get("functions") or [])
    if cap:
        funcs = funcs[:max_func]
    if not funcs:
        funcs = [{"stmts": []}]
    out = []
    for f_id, fn in enumerate(funcs):
        stmts = fn.get("stmts", []) or []
        if cap:
            stmts = stmts[:max_s]
        if cap and f_id == 0 and not stmts and len(funcs) == 1:
            stmts = [{"tokens": [], "text": ""}]
        out += [(s.get("tokens", []) or [], s.get("text", "") or "", call_nodes_of(s)) for s in stmts]
    return out


def analyze_one(row: dict, g, dump: dict | None, gcfg: dict) -> dict:
    import torch
    max_hops = gcfg["taint"]["max_hops"]
    x = g["stmt"].x
    S = int(x.shape[0])
    fl_src = (x[:, COL_SRC] > 0.5).tolist(); fl_sink = (x[:, COL_SINK] > 0.5).tolist()
    fl_dec = (x[:, COL_DEC] > 0.5).tolist(); fl_dir = (x[:, COL_DIRECT] > 0.5).tolist()
    role = g["stmt"].role.tolist()
    ei = lambda et: [tuple(p) for p in g[et].edge_index.t().tolist()]  # noqa: E731
    seq, cfg_e, dfg = ei(("stmt", "seq", "stmt")), ei(("stmt", "cfg", "stmt")), ei(("stmt", "dfg", "stmt"))
    calls = ei(("func", "call", "func"))
    func_of = [0] * S
    for s, f in ei(("stmt", "in", "func")):
        func_of[s] = f
    pos = g["stmt", "sem_pos", "stmt"].edge_index
    cand = g["stmt", "cand", "stmt"].edge_index
    n_rule = int(pos.shape[1])
    n_rule_in_cand = int(torch.isin(pos[0] * S + pos[1], cand[0] * S + cand[1]).sum()) if n_rule and cand.numel() else 0

    has_src, has_sink = any(fl_src), any(fl_sink)
    both = has_src and has_sink
    n_direct = sum(fl_dir)
    # Phủ CANDIDATE (cổng): cạnh cand i->j với i cờ source, j cờ sink CHẶT (multi-hot trong stmt.x);
    # bản nới tính cả sink chỉ-ứng-viên (role==4). Gồm mọi cặp trong-hàm + bridge arg/return exact|fallback.
    cl = cand.t().tolist() if cand.numel() else []
    n_ct = sum(1 for i, j in cl if fl_src[i] and fl_sink[j])
    n_ct_any = sum(1 for i, j in cl if fl_src[i] and (fl_sink[j] or role[j] == 4))
    r = {
        "sample_id": row["sample_id"], "label": row["label"], "source": row["source"], "role": row.get("role", ""),
        "status": row.get("status", ""), "n_stmt": S, "n_func": int(g["func"].num_nodes),
        "a_src": int(has_src), "b_sink": int(has_sink), "c_both": int(both),
        "n_rule_pairs": n_rule, "n_rule_in_cand": n_rule_in_cand,
        "d_pair": int(both and n_rule > 0), "d_pair_in_cand": int(both and n_rule_in_cand > 0),
        "e_direct": int(both and n_direct > 0), "n_direct_stmts": n_direct, "has_direct_any": int(n_direct > 0),
        "f_none": int(both and n_rule == 0 and n_direct == 0),
        "n_cand_typed": n_ct, "n_cand_typed_any": n_ct_any,
        "dc_cand": int(both and n_ct > 0), "dc_cand_any": int(both and n_ct_any > 0),
        "f_cand_none": int(both and n_ct == 0 and n_direct == 0),
        "cause": "", "mechanism": "", "min_hops": "", "call_connected": "", "via_decoder": "",
        "seed_miss": "", "seed_miss_kinds": "", "seed_miss_tokens": "",
        "file_suspect_src": "", "file_suspect_sink": "", "raw_c_both": "", "trunc_lost_both": "",
        "n_cand": int(cand.shape[1]), "n_cand_full": int(g.n_cand_full), "cand_capped": int(g.cand_capped),
        "align_ok": "", "b_sink_literal_only": "",
    }

    # --- token gốc (dump lại, chỉ đọc) + kiểm chứng căn khớp
    sus = None
    if dump is not None:
        flat = _flat_stmts(dump, gcfg["max_func_per_file"], gcfg["max_stmt_per_block"])
        ok = len(flat) == S and all(
            (("source" in (rl := token_roles(t, cn))) == fl_src[i]) and (("sink" in rl) == fl_sink[i])
            and (("decode" in rl) == fl_dec[i]) for i, (t, _, cn) in enumerate(flat))
        r["align_ok"] = int(ok)
        raw = _flat_stmts(dump, 0, 0, cap=False)
        raw_roles = set().union(*(token_roles(t, cn) for t, _, cn in raw)) if raw else set()
        r["raw_c_both"] = int({"source", "sink"} <= raw_roles)
        r["trunc_lost_both"] = int(r["raw_c_both"] == 1 and not both)
        if ok:
            sus = [stmt_suspects(t, txt, cn) for t, txt, cn in flat]
            r["file_suspect_src"] = int(any(k == "source" for ss in sus for k, _, _ in ss))
            r["file_suspect_sink"] = int(any(k == "sink" for ss in sus for k, _, _ in ss))
            # có tên sink nhưng KHÔNG có sink thật -> mọi tên sink chỉ ở literal/identifier (luật call node đã loại)
            r["b_sink_literal_only"] = int(not has_sink and any(has_sink_name(t) for t, _, _ in flat))

    if not (r["f_none"] or r["f_cand_none"]):
        return r

    # --- phân loại nguyên nhân cho (f)
    src = [i for i in range(S) if role[i] == 1]
    snk = [i for i in range(S) if role[i] == 2]
    f_src, f_snk = {func_of[i] for i in src}, {func_of[i] for i in snk}
    shared = f_src & f_snk
    if not shared:
        r["cause"] = "ii_cross_function"
        cadj = _adj(r["n_func"], calls)          # có hướng, theo cả hai chiều src->sink hoặc sink->src
        r["call_connected"] = int(bool(f_snk & set(_bfs(cadj, sorted(f_src))))
                                  or bool(f_src & set(_bfs(cadj, sorted(f_snk)))))
    else:
        r["cause"] = "i_global_main" if shared == {0} else "same_fn"
    adj = _adj(S, seq, cfg_e, dfg)
    dist = _bfs(adj, src)
    hops = [dist[k] for k in snk if k in dist]
    if hops:
        r["min_hops"] = min(hops)
    if shared:
        r["mechanism"] = ("beyond_hops" if hops and min(hops) > max_hops
                          else "no_forward_path" if not hops else "unexplained")
    dadj = _adj(S, dfg)
    dec_hit = [i for i in _bfs(dadj, src) if fl_dec[i]]
    r["via_decoder"] = int(bool(dec_hit) and any(k in _bfs(dadj, dec_hit) for k in snk))
    if sus is not None:
        fwd = _bfs(adj, src, max_hops)
        bwd = _bfs(_adj(S, seq, cfg_e, dfg, reverse=True), snk, max_hops)
        hits = [(k, t, tok) for i in fwd for k, t, tok in sus[i] if k == "sink"]
        hits += [(k, t, tok) for i in bwd for k, t, tok in sus[i] if k == "source"]
        r["seed_miss"] = int(bool(hits))
        r["seed_miss_kinds"] = "|".join(sorted({f"{k}:{t}" for k, t, _ in hits}))
        r["seed_miss_tokens"] = "|".join(sorted({tok for _, _, tok in hits}))[:200]
    return r


def analyze_chunk(rows: list[dict], gcfg: dict, pcfg: dict | None) -> list[dict]:
    import torch
    torch.set_num_threads(1)
    feats = ROOT / gcfg["_features_dir"]
    dumps = {}
    if pcfg is not None:
        from hipag.parsing.php_ast import dump_batch
        paths = [str(ROOT / r["path"]) for r in rows]
        dumps = dict(dump_batch(paths, pcfg["php_bin"], str(ROOT / pcfg["phpparser_entry"]), chunk=len(paths),
                                deobf=bool(pcfg.get("deobf", True)),   # cùng chế độ giải vỏ với lúc dựng đồ thị
                                workers=1, timeout=pcfg["timeout_s"]))
    out = []
    for r in rows:
        g = torch.load(feats / r["graph_path"], weights_only=False)
        out.append(analyze_one(r, g, dumps.get(str(ROOT / r["path"])) if pcfg is not None else None, gcfg))
    return out


# ------------------------------------------------------------------------------------------- báo cáo
def _pct(n, d):
    return f"{n:6d} ({100 * n / d:5.1f}%)" if d else f"{n:6d} (  n/a )"


def _causes(F, p, max_hops, use_php, tag="(f)"):
    if F:
        nf = len(F)
        cz = Counter(r["cause"] for r in F)
        mech = lambda c: Counter(r["mechanism"] for r in F if r["cause"] == c)  # noqa: E731
        p(f"    Nguyên nhân {tag} [i/ii/same_fn loại trừ nhau, % trên {tag}]:")
        m = mech("i_global_main")
        p(f"      i   source&sink chỉ cùng ở <main> {_pct(cz['i_global_main'], nf)}  "
          f"-> cơ chế: beyond_hops(>{max_hops}) {m['beyond_hops']}, no_forward_path {m['no_forward_path']}, "
          f"unexplained {m['unexplained']}")
        cc = sum(1 for r in F if r["cause"] == "ii_cross_function" and r["call_connected"] == 1)
        p(f"      ii  khác hàm (cross-function)     {_pct(cz['ii_cross_function'], nf)}  -> có đường E_call nối: {cc}")
        m = mech("same_fn")
        p(f"      --  cùng một hàm thường           {_pct(cz['same_fn'], nf)}  "
          f"-> beyond_hops {m['beyond_hops']}, no_forward_path {m['no_forward_path']}, unexplained {m['unexplained']}")
        p(f"      iii qua chuỗi DFG có decoder (chồng lấn) {_pct(sum(r['via_decoder'] == 1 for r in F), nf)}")
        if use_php:
            Fa = [r for r in F if r["align_ok"] == 1]
            sm = [r for r in Fa if r["seed_miss"] == 1]
            kinds = Counter(k for r in sm for k in r["seed_miss_kinds"].split("|") if k)
            toks = Counter(t for r in sm for t in r["seed_miss_tokens"].split("|") if t)
            p(f"      iv  seed-miss trong cửa sổ (chồng lấn) {_pct(len(sm), len(Fa))} trên {len(Fa)} file căn khớp")
            p(f"          loại: {dict(kinds.most_common())}")
            p(f"          token hay gặp: {toks.most_common(12)}")
        hops = [r["min_hops"] for r in F if r["min_hops"] != ""]
        if hops:
            p(f"    min_hops source->sink (khi có đường): median {statistics.median(hops)}, "
              f"max {max(hops)}, n={len(hops)}")


def summarize(rows: list[dict], gcfg: dict, use_php: bool) -> str:
    L = []
    p = L.append
    max_hops, max_cand = gcfg["taint"]["max_hops"], gcfg["taint"]["max_cand"]
    for lab, name in (("0", "BENIGN"), ("1", "WEBSHELL")):
        R = [r for r in rows if str(r["label"]) == lab]
        N = len(R)
        if not N:
            continue
        C = [r for r in R if r["c_both"]]
        F = [r for r in C if r["f_none"]]
        nc = len(C)
        p(f"\n=== {name}: {N} đồ thị ===")
        p(f"(a) có token source            {_pct(sum(r['a_src'] for r in R), N)}")
        p(f"(b) có token sink              {_pct(sum(r['b_sink'] for r in R), N)}")
        p(f"(c) có cả hai                  {_pct(nc, N)}")
        p(f"  (d) trong (c): ≥1 cặp luật    {_pct(sum(r['d_pair'] for r in C), nc)}"
          f"   | còn trong tập ứng viên (rule_e_sem/warmup dùng được): {_pct(sum(r['d_pair_in_cand'] for r in C), nc)}")
        p(f"  (e) trong (c): direct flag    {_pct(sum(r['e_direct'] for r in C), nc)}"
          f"   | cả (d) lẫn (e): {sum(r['d_pair'] and r['e_direct'] for r in C)}")
        p(f"  (f) trong (c): không cặp, không cờ {_pct(len(F), nc)}")
        _causes(F, p, max_hops, use_php)
        Fc = [r for r in C if r["f_cand_none"]]
        dcc = sum(r["dc_cand"] for r in C)
        p("  --- PHỦ CANDIDATE (CỔNG): (c) có ≥1 cặp ứng viên source->sink (exact|fallback) HOẶC cờ direct ---")
        p(f"  (d') trong (c): ≥1 cặp ứng viên có kiểu {_pct(dcc, nc)}"
          f"   | nới (tính sink chỉ-ứng-viên): {_pct(sum(r['dc_cand_any'] for r in C), nc)}")
        p(f"  (e)  trong (c): direct flag           {_pct(sum(r['e_direct'] for r in C), nc)}"
          f"   | cả (d') lẫn (e): {sum(r['dc_cand'] and r['e_direct'] for r in C)}")
        p(f"  (f') trong (c): không ứng viên, không cờ {_pct(len(Fc), nc)}")
        p(f"  => (A) PHỦ CANDIDATE strict (tới sink chặt) = {_pct(nc - len(Fc), nc)}")
        Fb = [r for r in C if not r["dc_cand_any"] and not r["e_direct"]]
        p(f"  => (B) PHỦ CANDIDATE broad (tới sink chặt|chỉ-ứng-viên) = {_pct(nc - len(Fb), nc)}")
        _causes(Fc, p, max_hops, use_php, tag="(f') strict")
        if Fb:
            p(f"    (f'') broad: {len(Fb)} file -> nguyên nhân: {dict(Counter(r['cause'] for r in Fb))}")
        if use_php:
            Ra = [r for r in R if r["align_ok"] == 1]
            notc = [r for r in Ra if not r["c_both"]]
            would = [r for r in notc if (r["a_src"] or r["file_suspect_src"]) and (r["b_sink"] or r["file_suspect_sink"])]
            p(f"  seed-miss mức file (ngoài c): trong {len(notc)} file KHÔNG thuộc (c), "
              f"{len(would)} sẽ thành (c) nếu mở rộng seed")
            p(f"  mất (c) do cắt max_func/max_stmt: {sum(r['trunc_lost_both'] == 1 for r in R)}")
            lit = [r for r in Ra if r["b_sink_literal_only"] == 1]
            p(f"  tên sink CHỈ ở literal/identifier (luật call node loại khỏi (b)): {len(lit)} file")
        cap = [r for r in R if r["cand_capped"]]
        p(f"  cand_capped: {_pct(len(cap), N)} chạm cap"
          + (f"; n_cand sau cap = {sorted({r['n_cand'] for r in cap})}; n_cand_full median "
             f"{int(statistics.median(r['n_cand_full'] for r in cap))}, max {max(r['n_cand_full'] for r in cap)}"
             if cap else ""))
        p(f"  direct_source_sink=1: {sum(r['has_direct_any'] for r in R)} đồ thị, "
          f"{sum(r['n_direct_stmts'] for r in R)} statement")
    p("\n=== TOÀN TẬP ===")
    p(f"đồ thị: {len(rows)}; max_cand (cap) = {max_cand}; max_hops = {max_hops}")
    p(f"cand_capped: {sum(r['cand_capped'] for r in rows)} đồ thị")
    p(f"direct_source_sink=1: {sum(r['has_direct_any'] for r in rows)} đồ thị, "
      f"{sum(r['n_direct_stmts'] for r in rows)} statement")
    if use_php:
        al = [r["align_ok"] for r in rows]
        p(f"căn khớp dump lại vs .pt: {al.count(1)}/{len(rows)} OK (lệch: {al.count(0)})")
    sc = Counter(r["status"] for r in rows if r["f_none"])
    p(f"parse status của (f): {dict(sc)}")
    return "\n".join(L)


FIELDS = ["sample_id", "label", "source", "role", "status", "n_stmt", "n_func", "a_src", "b_sink", "c_both",
          "n_rule_pairs", "n_rule_in_cand", "d_pair", "d_pair_in_cand", "e_direct", "n_direct_stmts",
          "has_direct_any", "f_none", "n_cand_typed", "n_cand_typed_any", "dc_cand", "dc_cand_any", "f_cand_none",
          "cause", "mechanism", "min_hops", "call_connected", "via_decoder",
          "seed_miss", "seed_miss_kinds", "seed_miss_tokens", "file_suspect_src", "file_suspect_sink",
          "raw_c_both", "trunc_lost_both", "b_sink_literal_only", "n_cand", "n_cand_full", "cand_capped",
          "align_ok"]


def main(args):
    cfg = load_config(ROOT / args.config, root=ROOT)
    from hipag.graph.hierarchical_graph import DEFAULT_GRAPH_CFG
    from hipag.utils.config import deep_merge
    from hipag.data.build import resolve_graph_cfg
    gcfg = deep_merge(DEFAULT_GRAPH_CFG, resolve_graph_cfg(cfg)["graph"])   # đúng cấu hình builder (kể cả esem:)
    gcfg["_features_dir"] = cfg["out_small_dir"]
    with open(ROOT / args.manifest, newline="") as f:
        man = {r["sample_id"]: r for r in csv.DictReader(f)}
    with open(ROOT / cfg["out_stats"], newline="") as f:
        stats = list(csv.DictReader(f))
    rows = []
    for s in stats:
        m = man.get(s["sample_id"])
        if m is None:
            continue
        rows.append({**s, "role": m.get("role", ""), "label": m["label"]})
    missing = len(man) - len(rows)
    rows = rows[: args.limit] if args.limit else rows
    print(f"manifest {len(man)} mẫu; có đồ thị {len(rows)} (thiếu {missing}); dump PHP: {not args.no_php}", flush=True)

    pcfg = None if args.no_php else cfg["parser"]
    chunks = [rows[i:i + args.chunk] for i in range(0, len(rows), args.chunk)]
    out = []
    with ProcessPoolExecutor(args.workers) as ex:
        futs = [ex.submit(analyze_chunk, c, gcfg, pcfg) for c in chunks]
        for k, fu in enumerate(as_completed(futs), 1):
            out += fu.result()
            if k % 20 == 0 or k == len(futs):
                print(f"  {k}/{len(futs)} chunk", flush=True)
    order = {r["sample_id"]: i for i, r in enumerate(rows)}
    out.sort(key=lambda r: order[r["sample_id"]])

    dst = ROOT / args.out
    with open(dst, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(out)
    print(summarize(out, gcfg, not args.no_php))
    print(f"\n-> {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/dataset/build_graphs.yaml")
    ap.add_argument("--manifest", default="experiments/dataset/manifest.csv")
    ap.add_argument("--out", default="experiments/dataset/esem_coverage.csv")
    ap.add_argument("--no-php", action="store_true", help="không dump lại PHP (bỏ iv + phần mất do cắt)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=32)
    main(ap.parse_args())
