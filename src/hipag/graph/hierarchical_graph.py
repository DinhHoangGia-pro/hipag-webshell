"""Lắp đồ thị phân cấp statement->function->file thành PyG HeteroData.

Hai bước tách rời:
  1. PHP --(parsing/)--> IR  (TODO Bước 13–14: AST nikic -> IR; chưa làm trong phiên này)
  2. IR  --build_hetero_from_ir--> HeteroData   (đã làm; dữ liệu giả cũng đi qua đây)

IR (dict, chỉ số statement là CỤC BỘ trong hàm):
    {
      "functions": [ {"name": str,
                      "stmts": [{"kind": str, "text": str, "tokens": [str],
                                 "calls": [str], "constructs": [str], ...}, ...],   # call node -> luật sink
                      "cfg": [(i, j), ...], "dfg": [(i, j), ...]}, ... ],   # functions[0] = phạm vi file
      "calls":    [(f_src, f_dst), ...],      # chỉ số function
      "includes": [(f_src, f_dst), ...],
      "source_text": str,
    }

Mỗi statement có thể mang thêm defs/uses/calls/callargs, mỗi function thêm params (dump_ast.php mới) —
dùng cho bridge taint liên thủ tục arg->param. Thiếu -> nhánh fallback (có đếm), hoặc bỏ qua nếu thiếu defs/uses.

Cặp E_sem (NHÃN CHẶT + ỨNG VIÊN NỚI, xem graph/taint_seeds.py):
  cand    = ứng viên có kiểu (source -> sink chặt hoặc sink chỉ-ứng-viên; trong-hàm trong cửa sổ esem_hop, hoặc
            bridge liên thủ tục) ∪ ứng viên generic (mọi cặp tới được trong cửa sổ). Cap THÔNG MINH: giữ cặp có kiểu
            trước, phần còn lại lấy ngẫu nhiên từ generic.
  sem_pos = CHỈ source -> sink CHẶT (trong-hàm tới được, hoặc bridge). sem_neg không bao giờ chứa cặp có kiểu.

HeteroData đầu ra:
    stmt.x [S, NODE_FEAT_DIM] float, stmt.x_tok [S, L] long (0=PAD), stmt.role [S] long (0 none,1 src,2 sink,3 dec)
    func.num_nodes = F
    edges: seq, skip, cfg, dfg, cand, sem_pos, sem_neg (stmt->stmt); in (stmt->func); call, include (func->func)
    global_x [1, GLOBAL_FEAT_DIM], y [1] float (nếu có nhãn)
    n_cand_full [1] long (số ứng viên trước cap), cand_capped [1] bool (max_cand có cắt không),
    n_typed_pairs / n_typed_cut [1] (cặp có kiểu / số bị cap cắt — phải ~0),
    n_bridged_crossfn [1] = tổng cặp liên thủ tục (hai chiều, khử trùng);
    n_bridged_arg_carried / n_bridged_fallback [1]   : chiều arg->param (source ở caller -> sink ở callee)
    n_bridged_return_exact / n_bridged_return_fallback [1] : chiều return->callsite (source ở callee -> sink ở caller)
    stmt.deobf [S] bool — statement ghép từ mã giải vỏ TĨNH (UPG-02, tools/php/deobf_lib.php; không vào x);
    n_deobf_stmts / n_deobf_folded / n_deobf_grafted / n_deobf_skipped [1] (log giải vỏ mức file)
"""
from __future__ import annotations

import random

import torch
from torch_geometric.data import HeteroData

from ..model.taint_predictor import build_seed_pairs
from ..parsing.call_include_graph import callee_index
from .edges import CAND, FUNC, IN_FUNC, PYG_EDGE, SEM_NEG, SEM_POS, STMT
from .node_features import global_features, node_vector, token_ids
from .taint_seeds import call_nodes_of, classify_token, is_candidate_sink, primary_role, reachable_within, token_roles

ROLE_ID = {None: 0, "source": 1, "sink": 2, "decode": 3, "cand_sink": 4}

DEFAULT_GRAPH_CFG = {
    "skip_window_delta": 2,     # E_skip: i -> i+2..i+δ
    "max_stmt_per_block": 200,  # cắt statement mỗi function
    "max_func_per_file": 50,
    "vocab_size": 4096,
    "max_tok_len": 32,
    "taint": {
        # 4 khoá dưới lấy từ configs/model/hipag_base.yaml `esem:` qua graph_cfg_with_esem (giá trị ở đây chỉ
        # là mặc định dự phòng, test_esem_mechanisms kiểm tra luôn khớp yaml).
        "max_hops": 12,         # esem_hop: cửa sổ CFG∪DFG∪E_seq cho cặp ứng viên/positive trong-hàm
        "max_cand": 4096,       # cap số cặp ứng viên E_sem mỗi file (cap thông minh: cặp có kiểu trước)
        "interproc_depth": 2,   # số call-hop tối đa khi bridge liên thủ tục
        "cross_function": True,
        "neg_per_pos": 5,
        "max_pos": 4096,
        "hard_frac": 0.5,
    },
}

# hipag_base.yaml `esem:` -> khoá trong graph cfg["taint"]
ESEM_KEYS = {"esem_hop": "max_hops", "max_cand": "max_cand", "interproc_depth": "interproc_depth",
             "cross_function": "cross_function"}


def graph_cfg_with_esem(graph_cfg: dict | None, model_cfg: dict | None) -> dict:
    """Trộn khối `esem:` của config model (MỘT nguồn: configs/model/hipag_base.yaml) vào graph cfg của builder."""
    esem = (model_cfg or {}).get("esem", {})
    unknown = set(esem) - set(ESEM_KEYS)
    if unknown:
        raise KeyError(f"esem: khoá không hỗ trợ {sorted(unknown)}; có {sorted(ESEM_KEYS)}")
    out = dict(graph_cfg or {})
    out["taint"] = {**out.get("taint", {}), **{ESEM_KEYS[k]: v for k, v in esem.items()}}
    return out


def _cfg(cfg: dict | None) -> dict:
    from ..utils.config import deep_merge
    return deep_merge(DEFAULT_GRAPH_CFG, cfg or {})


# ------------------------------------------------------------------ bridge taint liên thủ tục (arg -> param)
def _source_vars(tokens) -> set[str]:
    """Tên biến nguồn trong statement ('_POST'...). Nguồn không phải biến (getenv(), 'php://input') -> '*'."""
    out = set()
    for t in tokens:
        if classify_token(t) == "source":
            out.add(t[1:] if t.startswith("$") else "*")
    return out


def _prep_fn(fn_stmts, dfg_local, params, names_known):
    n = len(fn_stmts)
    succ = [[] for _ in range(n)]
    pred = [[] for _ in range(n)]
    for i, j in dfg_local:
        succ[i].append(j); pred[j].append(i)
    has_du = n > 0 and all("uses" in st for st in fn_stmts)
    callsites = []
    for i, st in enumerate(fn_stmts):
        if st.get("callargs") is not None:                       # dump mới: có đối số từng lời gọi
            callsites += [(i, (ca.get("name") or "").lower(), [set(a) for a in ca.get("args", [])])
                          for ca in st["callargs"]]
        elif st.get("calls"):
            callsites += [(i, c.lower(), None) for c in st["calls"]]
        else:                                                    # chỉ có token: tên + '('
            tk = st.get("tokens", [])
            callsites += [(i, t.lower(), None) for k, t in enumerate(tk)
                          if k + 1 < len(tk) and tk[k + 1] == "(" and t.lower() in names_known]
    return {"n": n, "succ": succ, "pred": pred, "has_du": has_du, "params": params, "callsites": callsites,
            "tokens": [st.get("tokens", []) for st in fn_stmts],
            "kinds": [st.get("kind", "") for st in fn_stmts],
            "defs": [set(st.get("defs") or []) for st in fn_stmts],
            "uses": [set(st.get("uses") or []) for st in fn_stmts]}


def _closure(P, seeds):
    T, q = set(seeds), list(seeds)
    while q:
        u = q.pop()
        for v in P["succ"][u]:
            if v not in T:
                T.add(v); q.append(v)
    return T


def _tainted_vars(P, c, T, seed_vars) -> set[str]:
    tv = set(seed_vars.get(c, ()))
    for d in P["pred"][c]:
        if d in T:
            tv |= (P["defs"][d] & P["uses"][c]) if P["has_du"] else {"*"}
    return tv


def bridge_cross_function(prep, offs, names, roles_ms, max_depth: int) -> dict:
    """Cặp (source ở caller -> sink ở callee) qua E_call, GATED theo tham số.

    exact   : call site có callargs, callee có params, có defs/uses -> chỉ bridge khi biến nhiễm nằm ở đối số j
              và trong callee tham số j tới được một sink theo DFG.
    fallback: thiếu callargs hoặc params -> bridge khi biến nhiễm được truyền (tại call site có biến nhiễm)
              VÀ callee có sink tới được từ MỘT tham số. Cần defs/uses ở callee; không có -> không bridge.
              Cặp fallback CHỈ là ứng viên, không bao giờ thành nhãn (giống chiều return).
    KHÔNG bao giờ bridge chỉ vì A gọi B. Trả {(src_gid, sink_gid): 'exact'|'fallback'} (exact thắng nếu cả hai).
    """
    by_name = callee_index(names)
    memo, stack = {}, set()

    def merge(dst, src, force=None):
        for g, m in src.items():
            m = force or m
            if dst.get(g) != "exact":
                dst[g] = m

    def entry_vars(P):
        return {v for u in range(P["n"]) for v in P["uses"][u]
                if not any(v in P["defs"][d] for d in P["pred"][u])}

    def callee_sinks(k, pidx, depth):
        key = (k, pidx, depth)
        if key in memo:
            return memo[key]
        if key in stack:
            return {}
        stack.add(key)
        P, res = prep[k], {}
        if P["has_du"]:
            params = P["params"]
            if pidx is None:
                pn = {p for p in params if p} if params else entry_vars(P)
            else:
                pn = {params[pidx]} if params and pidx < len(params) and params[pidx] else set()
            seed_vars = {}
            for p in pn:
                for u in range(P["n"]):
                    if p in P["uses"][u] and not any(p in P["defs"][d] for d in P["pred"][u]):
                        seed_vars.setdefault(u, set()).add(p)
            T = _closure(P, list(seed_vars))
            for u in T:
                if is_candidate_sink(roles_ms[offs[k] + u]):
                    res[offs[k] + u] = "exact"
            if depth > 1:
                for c, name, args in P["callsites"]:
                    if c in T:
                        tv = _tainted_vars(P, c, T, seed_vars)
                        for g in by_name.get(name, ()):
                            if g != k and tv:
                                merge(res, resolve(tv, args, g, depth - 1))
        memo[key] = res
        stack.discard(key)
        return res

    def resolve(tv, args, g, depth):
        Pg = prep[g]
        if args is not None and Pg["params"] is not None and "*" not in tv:
            out = {}
            for j, av in enumerate(args):
                if av & tv and j < len(Pg["params"]):
                    merge(out, callee_sinks(g, j, depth))
            return out
        if args is not None and "*" not in tv and not any(av & tv for av in args):
            return {}                                           # có danh sách đối số và không đối số nào nhiễm
        out = {}
        merge(out, callee_sinks(g, None, depth), force="fallback")
        return out

    pairs: dict[tuple[int, int], str] = {}
    for k, P in enumerate(prep):
        for s in range(P["n"]):
            if "source" not in roles_ms[offs[k] + s]:
                continue
            seed_vars = {s: _source_vars(prep[k]["tokens"][s]) or {"*"}}
            T = _closure(P, [s])
            for c, name, args in P["callsites"]:
                if c not in T:
                    continue
                tv = _tainted_vars(P, c, T, seed_vars)
                if not tv:
                    continue
                for g in by_name.get(name, ()):
                    if g == k:
                        continue
                    for gid, mode in resolve(tv, args, g, max_depth).items():
                        key = (offs[k] + s, gid)
                        if pairs.get(key) != "exact":
                            pairs[key] = mode
    return pairs


def bridge_return(prep, offs, names, roles_ms, max_depth: int) -> dict:
    """Chiều RETURN -> callsite (đối xứng arg->param): callee g trả về giá trị nhiễm từ source (taint theo DFG
    tới một statement Return của g), và tại call site c trong caller, giá trị đó chảy tới sink (c là sink,
    vd eval(g()), hoặc DFG từ c tới sink, vd $x = g(); eval($x)) -> cặp (source trong g -> sink ở caller).

    exact   : call site có callargs (dump mới) VÀ caller lẫn callee có defs/uses, VÀ mọi tầng lồng cũng exact.
    fallback: còn lại (call site chỉ tìm được qua 'calls'/token, hoặc thiếu defs/uses).
    Lồng tối đa max_depth call-hop: g trả về h() mà h trả về giá trị nhiễm (depth ≥ 2).
    Trả {(src_gid, sink_gid): 'exact'|'fallback'} (exact thắng nếu cả hai).
    """
    by_name = callee_index(names)
    memo, stack = {}, set()

    def merge(dst, src):
        for g, m in src.items():
            if dst.get(g) != "exact":
                dst[g] = m

    def returns_in(k, T):
        P = prep[k]
        return any(P["kinds"][u] == "Return" for u in T)

    def ret_sources(g, depth):
        """{source gid trong g (hoặc hàm g gọi): mode} có taint tới Return của g."""
        key = (g, depth)
        if key in memo:
            return memo[key]
        if key in stack:
            return {}
        stack.add(key)
        P, res = prep[g], {}
        mode = "exact" if P["has_du"] else "fallback"
        for s in range(P["n"]):
            if "source" in roles_ms[offs[g] + s] and returns_in(g, _closure(P, [s])):
                res[offs[g] + s] = mode
        if depth > 1:
            for c, name, args in P["callsites"]:
                for h in by_name.get(name, ()):
                    if h == g:
                        continue
                    sub = ret_sources(h, depth - 1)
                    if sub and returns_in(g, _closure(P, [c])):
                        exact_here = args is not None and P["has_du"]
                        merge(res, {r: (m if exact_here else "fallback") for r, m in sub.items()})
        memo[key] = res
        stack.discard(key)
        return res

    pairs: dict[tuple[int, int], str] = {}
    for k, P in enumerate(prep):
        for c, name, args in P["callsites"]:
            for g in by_name.get(name, ()):
                if g == k:
                    continue
                R = ret_sources(g, max_depth)
                if not R:
                    continue
                exact_here = args is not None and P["has_du"]
                sinks = [offs[k] + u for u in _closure(P, [c]) if is_candidate_sink(roles_ms[offs[k] + u])]
                for r, m in R.items():
                    mode = m if exact_here else "fallback"
                    for snk in sinks:
                        key = (r, snk)
                        if pairs.get(key) != "exact":
                            pairs[key] = mode
    return pairs


def _et(pairs) -> torch.Tensor:
    return (torch.tensor(pairs, dtype=torch.long).t().contiguous()
            if pairs else torch.empty(2, 0, dtype=torch.long))


def build_hetero_from_ir(ir: dict, cfg: dict | None = None, label: int | None = None, seed: int = 0) -> HeteroData:
    cfg = _cfg(cfg)
    tcfg = cfg["taint"]
    max_s, delta = cfg["max_stmt_per_block"], cfg["skip_window_delta"]

    funcs = list(ir.get("functions", []))[: cfg["max_func_per_file"]] or [{"name": "<main>", "stmts": []}]
    xs, toks, roles, roles_ms, in_func, deobf = [], [], [], [], [], []
    seq, skip, cfg_e, dfg_e = [], [], [], []
    fstmts, fdfg, offs = [], [], []
    for f_id, fn in enumerate(funcs):
        stmts = fn.get("stmts", [])[:max_s]
        if f_id == 0 and not stmts and len(funcs) == 1:
            stmts = [{"kind": "Nop", "text": "", "tokens": []}]   # file rỗng: giữ 1 nút để batch không vỡ
        off, n = len(xs), len(stmts)
        for p, st in enumerate(stmts):
            xs.append(node_vector(st, p, n))
            toks.append(token_ids(st.get("tokens", []), cfg["vocab_size"], cfg["max_tok_len"]))
            cn = call_nodes_of(st)                                  # luật call node (AST dump)
            roles.append(primary_role(st.get("tokens", []), cn))
            roles_ms.append(token_roles(st.get("tokens", []), cn))
            in_func.append((off + p, f_id))
            deobf.append(bool(st.get("deobfuscated", False)))
        seq += [(off + i, off + i + 1) for i in range(n - 1)]
        skip += [(off + i, off + i + d) for d in range(2, delta + 1) for i in range(n - d)]
        cfg_l = [(i, j) for i, j in fn.get("cfg", []) if 0 <= i < n and 0 <= j < n and i != j]
        dfg_l = [(i, j) for i, j in fn.get("dfg", []) if 0 <= i < n and 0 <= j < n and i != j]
        cfg_e += [(off + i, off + j) for i, j in cfg_l]
        dfg_e += [(off + i, off + j) for i, j in dfg_l]
        fstmts.append(stmts); fdfg.append(dfg_l); offs.append(off)

    S, F = len(xs), len(funcs)
    # Ứng viên generic: j tới được từ i trong cửa sổ esem_hop (cạnh trong-hàm -> ứng viên trong-hàm)
    reach = reachable_within(seq + cfg_e + dfg_e, S, tcfg["max_hops"])
    all_cand = [(i, j) for i in range(S) for j in sorted(reach.reach_set(i))]
    # Ứng viên CÓ KIỂU: source -> sink (chặt hoặc chỉ-ứng-viên), trong-hàm + bridge liên thủ tục
    typed = {c: None for c in all_cand if "source" in roles_ms[c[0]] and is_candidate_sink(roles_ms[c[1]])}
    bridged: dict = {}      # arg -> param
    bridged_ret: dict = {}  # return -> callsite
    if tcfg["cross_function"] and F > 1:
        names = [fn.get("name") for fn in funcs]
        known = {k for k in callee_index(names)}
        prep = [_prep_fn(fstmts[k], fdfg[k], funcs[k].get("params"), known) for k in range(F)]
        bridged = bridge_cross_function(prep, offs, names, roles_ms, int(tcfg["interproc_depth"]))
        bridged_ret = bridge_return(prep, offs, names, roles_ms, int(tcfg["interproc_depth"]))
        typed.update(dict.fromkeys(bridged))
        typed.update(dict.fromkeys(bridged_ret))
    typed_l = list(typed)
    all_set = set(all_cand)
    full = all_cand + [b for b in typed_l if b not in all_set]
    n_cand_full, cap, n_typed_cut = len(full), int(tcfg["max_cand"]), 0
    rng = random.Random(seed)
    if n_cand_full > cap:                     # cap thông minh: cặp có kiểu trước, generic lấp chỗ trống
        if len(typed_l) >= cap:
            cand, n_typed_cut = rng.sample(typed_l, cap), len(typed_l) - cap
        else:
            generic = [c for c in all_cand if c not in typed]
            cand = typed_l + rng.sample(generic, cap - len(typed_l))
    else:
        cand = full
    # NHÃN CHẶT, cùng quy tắc cả hai chiều: chỉ sink chặt + đường EXACT; cặp fallback chỉ là ứng viên.
    is_rule = lambda p, m: m == "exact" and roles[p[0]] == "source" and roles[p[1]] == "sink"  # noqa: E731
    extra_pos = [p for p, m in bridged.items() if is_rule(p, m)]
    extra_pos += [p for p, m in bridged_ret.items() if is_rule(p, m)]
    pos, neg = build_seed_pairs(roles, reach, neg_per_pos=tcfg["neg_per_pos"], max_pos=tcfg["max_pos"],
                                seed=seed, candidates=cand, hard_frac=tcfg["hard_frac"],
                                extra_pos=extra_pos, exclude_neg=set(typed))

    calls = [(a, b) for a, b in ir.get("calls", []) if a < F and b < F]
    incs = [(a, b) for a, b in ir.get("includes", []) if a < F and b < F]

    d = HeteroData()
    d[STMT].x = torch.tensor(xs, dtype=torch.float)
    d[STMT].x_tok = torch.tensor(toks, dtype=torch.long)
    d[STMT].role = torch.tensor([ROLE_ID[r] for r in roles], dtype=torch.long)
    d[FUNC].num_nodes = F
    d[PYG_EDGE["E_seq"]].edge_index = _et(seq)
    d[PYG_EDGE["E_skip"]].edge_index = _et(skip)
    d[PYG_EDGE["E_cfg"]].edge_index = _et(cfg_e)
    d[PYG_EDGE["E_dfg"]].edge_index = _et(dfg_e)
    d[PYG_EDGE["E_call"]].edge_index = _et(calls)
    d[PYG_EDGE["E_include"]].edge_index = _et(incs)
    d[CAND].edge_index = _et(cand)
    d[SEM_POS].edge_index = pos
    d[SEM_NEG].edge_index = neg
    d[IN_FUNC].edge_index = _et(in_func)
    d.n_cand_full = torch.tensor([n_cand_full])                       # trước khi cap
    d.cand_capped = torch.tensor([n_cand_full > cap])                 # max_cand có binding không
    d.n_typed_pairs = torch.tensor([len(typed_l)])
    d.n_typed_cut = torch.tensor([n_typed_cut])                       # cặp source->sink bị cap cắt (phải ~0)
    d.n_bridged_crossfn = torch.tensor([len(set(bridged) | set(bridged_ret))])
    d.n_bridged_arg_carried = torch.tensor([sum(m == "exact" for m in bridged.values())])
    d.n_bridged_fallback = torch.tensor([sum(m == "fallback" for m in bridged.values())])
    d.n_bridged_return_exact = torch.tensor([sum(m == "exact" for m in bridged_ret.values())])
    d.n_bridged_return_fallback = torch.tensor([sum(m == "fallback" for m in bridged_ret.values())])
    d[STMT].deobf = torch.tensor(deobf, dtype=torch.bool)
    dl = ir.get("deobf") or {}
    d.n_deobf_stmts = torch.tensor([sum(deobf)])
    d.n_deobf_folded = torch.tensor([int(dl.get("folded", 0))])
    d.n_deobf_grafted = torch.tensor([int(dl.get("grafted", 0))])
    d.n_deobf_skipped = torch.tensor([int(sum((dl.get("skipped") or {}).values()))])
    d.global_x = torch.tensor([global_features(ir.get("source_text", ""))], dtype=torch.float)
    if label is not None:
        d.y = torch.tensor([float(label)])
    return d


def build_hierarchical_graph(php_file: str, cfg: dict | None = None, label: int | None = None,
                             seed: int = 0, dump: dict | None = None) -> HeteroData:
    """PHP file -> HeteroData: dump_ast.php (nikic) -> ast_to_ir (CFG/DFG/call) -> build_hetero_from_ir.
    `dump` cho phép truyền kết quả dump_batch có sẵn (scripts/dataset/04_build_graphs.py)."""
    from ..parsing.php_ast import ast_to_ir, dump_ast, source_text_of
    if dump is None:
        dump = dump_ast(php_file)
    text = source_text_of(dump, php_file)      # bản chuẩn hoá — cùng bản dump_ast.php đã parse
    return build_hetero_from_ir(ast_to_ir(dump, text), cfg, label=label, seed=seed)
