"""Nâng độ phủ E_sem: nhãn chặt + ứng viên nới, bridge liên thủ tục arg->param, cap thông minh, hop từ config.
Mỗi cơ chế một ca trên IR/HeteroData GIẢ (không dùng corpus)."""
import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml

from hipag.data.build import STAT_FIELDS, esem_stats, resolve_graph_cfg
from hipag.graph.edges import CAND, SEM_NEG, SEM_POS, STMT
from hipag.graph.hierarchical_graph import (DEFAULT_GRAPH_CFG, ESEM_KEYS, ROLE_ID, build_hetero_from_ir,
                                            graph_cfg_with_esem)
from hipag.graph.taint_seeds import (CANDIDATE_SINKS, RULE_SINKS, classify_token, has_e_modifier,
                                     primary_role, token_roles)
from hipag.utils.config import load_config

ROOT = Path(__file__).resolve().parents[1]
pairs = lambda ei: set(map(tuple, ei.t().tolist()))  # noqa: E731


def st(tokens, defs=(), uses=(), callargs=None, kind="Expression", calls=(), constructs=()):
    """Statement IR như dump_ast.php: call node thật = calls (+ tên trong callargs) ∪ constructs."""
    d = {"kind": kind, "text": " ".join(tokens), "tokens": list(tokens), "defs": list(defs),
         "uses": list(uses), "calls": list(calls) + [c["name"] for c in (callargs or [])],
         "constructs": list(constructs)}
    if callargs is not None:
        d["callargs"] = callargs
    return d


def fn(name, stmts, dfg=(), params=None):
    return {"name": name, "params": params, "stmts": stmts,
            "cfg": [(i, i + 1) for i in range(len(stmts) - 1)], "dfg": list(dfg)}


def filler(k):
    return [st(["echo", f"'f{i}'"]) for i in range(k)]


def build(ir, **taint):
    return build_hetero_from_ir(ir, {"taint": taint} if taint else None, label=1)


SRC = st(["$x", "=", "$_POST", "c"], defs=["x"], uses=["_POST"])          # nguồn: $x = $_POST['c']


# ------------------------------------------------------------------ [1] seed: nhãn chặt / ứng viên nới
def test_seed_sets_and_context_roles():
    assert set(RULE_SINKS) <= set(CANDIDATE_SINKS)
    assert classify_token("EVAL") == "sink" and classify_token("<dyncall>") == "sink"
    assert classify_token("fwrite") == "cand_sink" and classify_token("include") == "cond_sink"
    assert classify_token("$_SESSION") == "source" and classify_token("php://input") == "source"
    assert classify_token("array_map") is None                       # không còn là sink (không có trong 2 tập)
    INC, PR = {"include"}, {"preg_replace"}                          # call node thật (từ AST dump)
    assert token_roles(["include", "config.php"], INC) == set()       # include tĩnh: không phải sink
    assert token_roles(["include", "$page"], INC) == {"sink"}         # include động: sink chặt
    assert token_roles(["include", "$page"]) == set()                 # cùng token nhưng KHÔNG là construct
    assert token_roles(["preg_replace", "/x/e", "$r", "$s"], PR) == {"sink"}
    assert token_roles(["preg_replace", "/x/i", "$r", "$s"], PR) == set()
    assert has_e_modifier("{a}ie") and not has_e_modifier("/a/i") and not has_e_modifier("abc")
    FO = {"fopen"}
    assert token_roles(["fopen", "(", "$p", "r"], FO) == set()
    assert token_roles(["fopen", "(", "$p", "wb"], FO) == {"cand_sink"}
    assert token_roles(["fopen", "(", "$p", "$mode"], FO) == {"cand_sink"}   # không thấy chế độ -> nới
    assert primary_role(["fwrite", "(", "$f", "$_POST"], {"fwrite"}) == "source"   # sink > source > cand_sink


def test_candidate_sink_is_candidate_not_label_rule_sink_is_both():
    for sink_tok, node, is_rule in ((["fwrite", "(", "$fp", "$x"], {"calls": ["fwrite"]}, False),
                                    (["eval", "$x"], {"constructs": ["eval"]}, True)):
        d = build({"functions": [fn("<main>", [SRC, st(sink_tok, uses=["fp", "x"], **node)], dfg=[(0, 1)])]})
        assert (0, 1) in pairs(d[CAND].edge_index)                       # luôn là ứng viên có kiểu
        assert ((0, 1) in pairs(d[SEM_POS].edge_index)) is is_rule       # chỉ sink chặt mới thành nhãn
        assert (0, 1) not in pairs(d[SEM_NEG].edge_index)                # không bao giờ thành nhãn âm
        assert int(d[STMT].role[1]) == (ROLE_ID["sink"] if is_rule else ROLE_ID["cand_sink"])


# ------------------------------------------------------------------ phạm vi file + cửa sổ hop từ config
def test_file_scope_main_source_to_sink():
    main = [SRC] + filler(3) + [st(["eval", "$x"], uses=["x"], constructs=["eval"])]
    d = build({"functions": [fn("<main>", main, dfg=[(0, 4)])]})
    assert (0, 4) in pairs(d[SEM_POS].edge_index) and (0, 4) in pairs(d[CAND].edge_index)


def test_hop_window_reads_config():
    main = [SRC] + filler(9) + [st(["eval", "$y"], uses=["y"], constructs=["eval"])]      # cách 10 bước, chỉ nối bằng E_seq
    ir = {"functions": [fn("<main>", main)]}
    assert (0, 10) in pairs(build(ir)[SEM_POS].edge_index)            # mặc định esem_hop = 12
    assert (0, 10) not in pairs(build(ir, max_hops=8)[SEM_POS].edge_index)


# ------------------------------------------------------------------ [2] liên thủ tục arg->param
def _call(name, *args):
    return [{"name": name, "args": [list(a) for a in args]}]


def test_crossfn_arg_carried_exact():
    main = fn("<main>", [SRC, st(["foo", "(", "$x"], uses=["x"], callargs=_call("foo", ["x"]))], dfg=[(0, 1)])
    foo = fn("foo", [st(["eval", "$p"], uses=["p"], constructs=["eval"])], params=["p"])
    d = build({"functions": [main, foo]})
    assert (0, 2) in pairs(d[SEM_POS].edge_index) and (0, 2) in pairs(d[CAND].edge_index)
    assert int(d.n_bridged_arg_carried) == 1 and int(d.n_bridged_fallback) == 0


def test_crossfn_superglobal_passed_directly():
    main = fn("<main>", [st(["foo", "(", "$_POST", "c"], uses=["_POST"], callargs=_call("foo", ["_POST"]))])
    foo = fn("foo", [st(["system", "(", "$p"], uses=["p"], calls=["system"])], params=["p"])
    assert (0, 1) in pairs(build({"functions": [main, foo]})[SEM_POS].edge_index)


def test_crossfn_depth_limit():
    main = fn("<main>", [SRC, st(["foo", "(", "$x"], uses=["x"], callargs=_call("foo", ["x"]))], dfg=[(0, 1)])
    foo = fn("foo", [st(["bar", "(", "$p"], uses=["p"], callargs=_call("bar", ["p"]))], params=["p"])
    bar = fn("bar", [st(["system", "(", "$q"], uses=["q"], calls=["system"])], params=["q"])
    ir = {"functions": [main, foo, bar]}
    assert (0, 3) in pairs(build(ir)[SEM_POS].edge_index)                   # 2 call-hop, mặc định depth=2
    assert (0, 3) not in pairs(build(ir, interproc_depth=1)[SEM_POS].edge_index)


@pytest.mark.parametrize("case", ["untainted_arg", "tainted_to_nonsink_param", "no_args", "sink_ignores_param"])
def test_crossfn_not_arg_carried_never_bridges(case):
    if case == "untainted_arg":                 # A gọi B nhưng truyền biến KHÔNG nhiễm
        call, dfg = st(["foo", "(", "$y"], uses=["y"], callargs=_call("foo", ["y"])), []
        foo = fn("foo", [st(["eval", "$p"], uses=["p"], constructs=["eval"])], params=["p"])
    elif case == "tainted_to_nonsink_param":    # biến nhiễm vào tham số a, sink chỉ dùng tham số b
        call, dfg = st(["foo", "(", "$x", "$y"], uses=["x", "y"], callargs=_call("foo", ["x"], ["y"])), [(0, 1)]
        foo = fn("foo", [st(["eval", "$b"], uses=["b"], constructs=["eval"])], params=["a", "b"])
    elif case == "no_args":                     # A gọi B() — chỉ vì A gọi B thì KHÔNG bridge
        call, dfg = st(["foo", "("], callargs=_call("foo")), [(0, 1)]
        foo = fn("foo", [st(["eval", "$p"], uses=["p"], constructs=["eval"])], params=["p"])
    else:                                       # B có sink nhưng sink không phụ thuộc tham số
        call, dfg = st(["foo", "(", "$x"], uses=["x"], callargs=_call("foo", ["x"])), [(0, 1)]
        foo = fn("foo", [st(["eval", "'1'"], constructs=["eval"])], params=["p"])
    d = build({"functions": [fn("<main>", [SRC, call], dfg=dfg), foo]})
    assert int(d.n_bridged_crossfn) == 0
    cross = {p for p in pairs(d[CAND].edge_index) | pairs(d[SEM_POS].edge_index) if p[1] >= 2}
    assert not cross


def test_crossfn_fallback_when_no_callargs_logged():
    call = st(["foo", "(", "$x"], uses=["x"])                    # dump cũ: không có callargs
    call["calls"] = ["foo"]
    foo = fn("foo", [st(["eval", "$p"], uses=["p"], constructs=["eval"])], params=["p"])
    d = build({"functions": [fn("<main>", [SRC, call], dfg=[(0, 1)]), foo]})
    # fallback CHỈ là ứng viên: có trong cand, KHÔNG thành nhãn dương, cũng không thành nhãn âm
    assert (0, 2) in pairs(d[CAND].edge_index)
    assert (0, 2) not in pairs(d[SEM_POS].edge_index) and (0, 2) not in pairs(d[SEM_NEG].edge_index)
    assert int(d.n_bridged_fallback) == 1 and int(d.n_bridged_arg_carried) == 0
    # fallback vẫn GATED: call site không nhận biến nhiễm -> không bridge
    call2 = st(["foo", "(", "$y"], uses=["y"]); call2["calls"] = ["foo"]
    d2 = build({"functions": [fn("<main>", [SRC, call2]), foo]})
    assert int(d2.n_bridged_crossfn) == 0


def test_crossfn_candidate_sink_bridged_as_candidate_only():
    main = fn("<main>", [SRC, st(["foo", "(", "$x"], uses=["x"], callargs=_call("foo", ["x"]))], dfg=[(0, 1)])
    foo = fn("foo", [st(["fwrite", "(", "$h", "$p"], uses=["h", "p"], calls=["fwrite"])], params=["p"])
    d = build({"functions": [main, foo]})
    assert (0, 2) in pairs(d[CAND].edge_index) and (0, 2) not in pairs(d[SEM_POS].edge_index)
    assert (0, 2) not in pairs(d[SEM_NEG].edge_index)


def test_cross_function_flag_off():
    main = fn("<main>", [SRC, st(["foo", "(", "$x"], uses=["x"], callargs=_call("foo", ["x"]))], dfg=[(0, 1)])
    foo = fn("foo", [st(["eval", "$p"], uses=["p"], constructs=["eval"])], params=["p"])
    d = build({"functions": [main, foo]}, cross_function=False)
    assert int(d.n_bridged_crossfn) == 0 and (0, 2) not in pairs(d[SEM_POS].edge_index)


# ------------------------------------------------------------------ [3] cap thông minh
def test_smart_cap_keeps_typed_pair_drops_generic():
    main = [SRC] + filler(18) + [st(["eval", "$x"], uses=["x"], constructs=["eval"])]
    ir = {"functions": [fn("<main>", main, dfg=[(0, 19)])]}
    for seed in range(5):
        d = build_hetero_from_ir(ir, {"taint": {"max_cand": 5}}, label=1, seed=seed)
        cand = pairs(d[CAND].edge_index)
        assert bool(d.cand_capped) and len(cand) == 5 and int(d.n_cand_full) > 5
        assert (0, 19) in cand and int(d.n_typed_cut) == 0              # cặp source->sink luôn được giữ


def test_smart_cap_typed_overflow_is_logged():
    srcs = [st([f"$s{i}", "=", "$_GET", "k"], defs=[f"s{i}"], uses=["_GET"]) for i in range(3)]
    sinks = [st(["system", "(", f"$s{i}"], uses=[f"s{i}"], calls=["system"]) for i in range(3)]
    ir = {"functions": [fn("<main>", srcs + sinks)]}
    d = build(ir, max_cand=4)
    typed = int(d.n_typed_pairs)
    assert typed == 9 and int(d.n_typed_cut) == typed - 4
    roles = d[STMT].role.tolist()
    assert all(roles[i] == 1 and roles[j] == 2 for i, j in pairs(d[CAND].edge_index))   # chỉ còn cặp có kiểu


# ------------------------------------------------------------------ [4] config + [5] instrumentation
def test_esem_config_single_source():
    esem = yaml.safe_load(open(ROOT / "configs/model/hipag_base.yaml"))["esem"]
    assert esem == {"esem_hop": 12, "interproc_depth": 2, "max_cand": 4096, "cross_function": True}
    for k, v in esem.items():                                          # mặc định dự phòng KHÔNG lệch yaml
        assert DEFAULT_GRAPH_CFG["taint"][ESEM_KEYS[k]] == v
    g = graph_cfg_with_esem({"taint": {"neg_per_pos": 3}}, {"esem": {"esem_hop": 5}})
    assert g["taint"] == {"neg_per_pos": 3, "max_hops": 5}
    with pytest.raises(KeyError):
        graph_cfg_with_esem({}, {"esem": {"esem_hops": 5}})
    bcfg = resolve_graph_cfg(load_config(ROOT / "configs/dataset/build_graphs.yaml"))
    assert bcfg["graph"]["taint"]["max_hops"] == 12 and bcfg["graph"]["taint"]["cross_function"] is True


def test_instrumentation_fields():
    required = {"has_source", "has_sink", "has_both", "n_rule_pairs", "n_candidate_pairs", "n_cand_full",
                "cand_capped", "direct_source_sink_count", "n_bridged_crossfn", "n_bridged_arg_carried",
                "n_bridged_fallback", "n_typed_cut", "status"}
    assert required <= set(STAT_FIELDS)
    main = fn("<main>", [SRC, st(["foo", "(", "$x"], uses=["x"], callargs=_call("foo", ["x"])),
                         st(["eval", "$_GET"], uses=["_GET"], constructs=["eval"])], dfg=[(0, 1)])
    foo = fn("foo", [st(["eval", "$p"], uses=["p"], constructs=["eval"])], params=["p"])
    s = esem_stats(build({"functions": [main, foo]}))
    assert s["has_both"] == 1 and s["n_bridged_arg_carried"] == 1 and s["direct_source_sink_count"] == 1
    assert s["n_rule_pairs"] >= 1 and s["n_candidate_pairs"] >= s["n_rule_pairs"] and s["n_typed_cut"] == 0


def test_metadata_probe_exposes_cand_capped_and_status():
    spec = importlib.util.spec_from_file_location("metadata_probe", ROOT / "scripts/metadata_probe.py")
    mp = importlib.util.module_from_spec(spec); spec.loader.exec_module(mp)
    assert {"cand_capped", "status_ok", "status_recovered", "status_fallback"} <= set(mp.GRAPHMETA)
    f = dict(zip(mp.GRAPHMETA, mp.graphmeta_features({"status": "fallback_tokens", "cand_capped": "1"})))
    assert f["cand_capped"] == 1.0 and f["status_fallback"] == 1.0
    assert len(mp.graphmeta_features({"status": "ok"})) == len(mp.GRAPHMETA)   # graph_stats cũ thiếu cột -> 0


# ------------------------------------------------------------------ tích hợp dumper thật (file PHP tí hon)
@pytest.mark.skipif(not shutil.which("php") or not (ROOT / "vendor/autoload.php").exists(),
                    reason="cần php + vendor (nikic/php-parser)")
def test_dump_ast_params_callargs_end_to_end(tmp_path):
    from hipag.parsing.php_ast import ast_to_ir, dump_ast
    carried = tmp_path / "a.php"
    carried.write_text("<?php\nfunction run($cmd, $o) { $c = $cmd; eval($c); }\n$x = $_POST['c'];\nrun($x, 'k');\n")
    plain = tmp_path / "b.php"
    plain.write_text("<?php\nfunction run($cmd, $o) { eval($cmd); }\n$x = $_POST['c'];\nrun('ls', $x);\n")
    dump = dump_ast(str(carried))
    assert dump["functions"][1]["params"] == ["cmd", "o"]
    assert any(ca["name"] == "run" and ca["args"][0] == ["x"]
               for s in dump["functions"][0]["stmts"] for ca in s["callargs"])
    d = build_hetero_from_ir(ast_to_ir(dump, carried.read_text()), label=1)
    assert int(d.n_bridged_arg_carried) >= 1 and int(d.n_bridged_fallback) == 0
    roles = d[STMT].role.tolist()
    assert any(roles[i] == 1 and roles[j] == 2 for i, j in pairs(d[SEM_POS].edge_index))
    # $x nhiễm vào tham số $o (không tới sink); $cmd = 'ls' -> KHÔNG bridge
    d2 = build_hetero_from_ir(ast_to_ir(dump_ast(str(plain)), plain.read_text()), label=1)
    assert int(d2.n_bridged_crossfn) == 0


# ------------------------------------------------------------------ chiều RETURN -> callsite
def ret(tokens, uses=()):
    return st(tokens, uses=uses, kind="Return")


G_TAINTED = fn("g", [st(["$a", "=", "$_POST", "a"], defs=["a"], uses=["_POST"]), ret(["$a"], uses=["a"])],
               dfg=[(0, 1)])


def test_new_sources():
    for v in ("$HTTP_POST_VARS", "$HTTP_GET_VARS", "$HTTP_COOKIE_VARS", "$HTTP_REQUEST_VARS"):
        assert classify_token(v) == "source", v
    assert classify_token("$GLOBALS") is None                 # alias bảng ký hiệu, không phải input ngoài


def test_fallback_never_labels_both_directions():
    """Cùng quy tắc CHẶT cho hai chiều: exact -> nhãn; fallback -> chỉ ứng viên."""
    foo = fn("foo", [st(["eval", "$p"], uses=["p"], constructs=["eval"])], params=["p"])
    g = fn("g", [ret(["$_POST", "a"], uses=["_POST"])])
    for exact in (True, False):
        arg_call = st(["foo", "(", "$x"], uses=["x"], callargs=_call("foo", ["x"]) if exact else None)
        ret_call = st(["eval", "g", "("], constructs=["eval"], callargs=_call("g") if exact else None)
        if not exact:
            arg_call["calls"], ret_call["calls"] = ["foo"], ["g"]
        d = build({"functions": [fn("<main>", [SRC, arg_call, ret_call], dfg=[(0, 1)]), foo, g]})
        arg_pair, ret_pair = (0, 3), (4, 2)                    # main: 0,1,2 | foo: 3 | g: 4
        pos, cand = pairs(d[SEM_POS].edge_index), pairs(d[CAND].edge_index)
        assert arg_pair in cand and ret_pair in cand
        assert (arg_pair in pos) is exact and (ret_pair in pos) is exact
        assert int(d.n_bridged_arg_carried) == int(exact) and int(d.n_bridged_fallback) == int(not exact)
        assert int(d.n_bridged_return_exact) == int(exact) and int(d.n_bridged_return_fallback) == int(not exact)


def test_return_direct_into_sink_eval_g():
    main = fn("<main>", [st(["eval", "g", "("], constructs=["eval"], callargs=_call("g"))])
    g = fn("g", [ret(["$_POST", "a"], uses=["_POST"])])           # function g(){ return $_POST['a']; }
    d = build({"functions": [main, g]})
    assert (1, 0) in pairs(d[SEM_POS].edge_index) and (1, 0) in pairs(d[CAND].edge_index)
    assert int(d.n_bridged_return_exact) == 1 and int(d.n_bridged_return_fallback) == 0
    assert int(d.n_bridged_arg_carried) == 0 and int(d.n_bridged_crossfn) == 1


def test_return_via_variable_x_eq_g_then_eval():
    main = fn("<main>", [st(["$x", "=", "g", "("], defs=["x"], callargs=_call("g")),
                         st(["eval", "$x"], uses=["x"], constructs=["eval"])], dfg=[(0, 1)])
    d = build({"functions": [main, G_TAINTED]})              # g: $a = $_POST['a']; return $a;
    assert (2, 1) in pairs(d[SEM_POS].edge_index)            # source trong g (gid 2) -> eval ở caller (gid 1)
    assert int(d.n_bridged_return_exact) == 1


@pytest.mark.parametrize("case", ["return_untainted", "value_not_to_sink", "no_return"])
def test_return_untainted_never_bridges(case):
    g = G_TAINTED
    main_stmts, dfg = [st(["eval", "g", "("], constructs=["eval"], callargs=_call("g"))], []
    if case == "return_untainted":               # đọc $_POST nhưng trả hằng
        g = fn("g", [st(["$a", "=", "$_POST", "a"], defs=["a"], uses=["_POST"]), ret(["ok"])])
    elif case == "value_not_to_sink":            # giá trị trả về không chảy tới sink
        main_stmts = [st(["$x", "=", "g", "("], defs=["x"], callargs=_call("g")), st(["eval", "$y"], uses=["y"], constructs=["eval"])]
    else:                                        # g dùng $_POST nhưng không return
        g = fn("g", [st(["echo", "$_POST"], uses=["_POST"])])
    d = build({"functions": [fn("<main>", main_stmts, dfg=dfg), g]})
    assert int(d.n_bridged_return_exact) + int(d.n_bridged_return_fallback) == 0
    n_main = len(main_stmts)
    assert not {p for p in pairs(d[SEM_POS].edge_index) | pairs(d[CAND].edge_index)
                if p[0] >= n_main and p[1] < n_main}            # không có cặp callee -> caller


def test_return_fallback_is_candidate_only():
    call = st(["eval", "g", "("], constructs=["eval"]); call["calls"] = ["g"]          # dump cũ: không có callargs
    d = build({"functions": [fn("<main>", [call]), fn("g", [ret(["$_POST", "a"], uses=["_POST"])])]})
    assert (1, 0) in pairs(d[CAND].edge_index) and (1, 0) not in pairs(d[SEM_POS].edge_index)
    assert (1, 0) not in pairs(d[SEM_NEG].edge_index)
    assert int(d.n_bridged_return_fallback) == 1 and int(d.n_bridged_return_exact) == 0


def test_return_to_candidate_sink_is_candidate_only():
    main = fn("<main>", [st(["fwrite", "(", "$h", "g", "("], uses=["h"], callargs=_call("fwrite", ["h"], []) +
                            _call("g"))])
    d = build({"functions": [main, fn("g", [ret(["$_POST", "a"], uses=["_POST"])])]})
    assert (1, 0) in pairs(d[CAND].edge_index) and (1, 0) not in pairs(d[SEM_POS].edge_index)
    assert int(d.n_bridged_return_exact) == 1


def test_return_depth_limit():
    main = fn("<main>", [st(["eval", "g", "("], constructs=["eval"], callargs=_call("g"))])
    g = fn("g", [ret(["h", "("])])
    g["stmts"][0]["callargs"] = _call("h")                      # function g(){ return h(); }
    h = fn("h", [ret(["$_POST", "a"], uses=["_POST"])])         # function h(){ return $_POST['a']; }
    ir = {"functions": [main, g, h]}
    assert (2, 0) in pairs(build(ir)[SEM_POS].edge_index)                       # 2 call-hop, depth=2
    assert (2, 0) not in pairs(build(ir, interproc_depth=1)[SEM_POS].edge_index)


def test_return_stats_fields():
    assert {"n_bridged_return_exact", "n_bridged_return_fallback"} <= set(STAT_FIELDS)
    main = fn("<main>", [st(["eval", "g", "("], constructs=["eval"], callargs=_call("g"))])
    s = esem_stats(build({"functions": [main, fn("g", [ret(["$_POST", "a"], uses=["_POST"])])]}))
    assert s["n_bridged_return_exact"] == 1 and s["n_bridged_return_fallback"] == 0


@pytest.mark.skipif(not shutil.which("php") or not (ROOT / "vendor/autoload.php").exists(),
                    reason="cần php + vendor (nikic/php-parser)")
def test_dump_ast_return_end_to_end(tmp_path):
    from hipag.parsing.php_ast import ast_to_ir, dump_ast
    f = tmp_path / "r.php"
    f.write_text("<?php\nfunction g() { $a = $_POST['a']; return $a; }\neval(g());\n$x = g(); eval($x);\n")
    d = build_hetero_from_ir(ast_to_ir(dump_ast(str(f)), f.read_text()), label=1)
    assert int(d.n_bridged_return_exact) == 2 and int(d.n_bridged_return_fallback) == 0   # 2 sink ở caller
    roles, fn_of = d[STMT].role.tolist(), dict(map(tuple, d["stmt", "in", "func"].edge_index.t().tolist()))
    cross = [(i, j) for i, j in pairs(d[SEM_POS].edge_index) if fn_of[i] != fn_of[j]]
    assert len(cross) == 2 and all(roles[i] == 1 and roles[j] == 2 for i, j in cross)
    g = tmp_path / "s.php"                                         # trả hằng -> không bridge
    g.write_text("<?php\nfunction g() { $a = $_POST['a']; return 'ok'; }\neval(g());\n")
    d2 = build_hetero_from_ir(ast_to_ir(dump_ast(str(g)), g.read_text()), label=1)
    assert int(d2.n_bridged_return_exact) + int(d2.n_bridged_return_fallback) == 0


# ------------------------------------------------------------------ seed cuối: unserialize / extract / ob_start
from hipag.graph.node_features import N_NUMERIC, NODE_FEAT_DIM  # noqa: E402
from hipag.graph.taint_seeds import CALL_ONLY  # noqa: E402


def test_final_seed_lists():
    assert "unserialize" in RULE_SINKS and {"extract", "ob_start"} <= set(CANDIDATE_SINKS)
    assert "extract" not in RULE_SINKS and "ob_start" not in RULE_SINKS
    assert CALL_ONLY == {"unserialize", "extract", "ob_start"}


@pytest.mark.parametrize("tokens,calls,roles", [
    (["unserialize", "(", "$x"], {"unserialize"}, {"sink"}),             # call node -> sink chặt
    (["$f", "=", "unserialize"], set(), set()),                          # literal trùng tên -> không
    (["extract", "(", "$_POST"], {"extract"}, {"source", "sink"}),       # mảng source -> chặt
    (["extract", "(", "$HTTP_POST_VARS"], {"extract"}, {"source", "sink"}),
    (["extract", "(", "$d"], {"extract"}, {"cand_sink"}),                # mảng thường -> chỉ ứng viên
    (["echo", "extract"], set(), set()),
    (["ob_start", "(", "$cb"], {"ob_start"}, {"cand_sink"}),             # callback là biến -> ứng viên
    (["ob_start", "(", "ob_gzhandler"], {"ob_start"}, set()),            # callback literal -> không
    (["ob_start", "("], {"ob_start"}, set()),                            # không callback -> không
])
def test_final_seed_context_roles(tokens, calls, roles):
    assert token_roles(tokens, calls) == roles


def test_unserialize_is_label():
    d = build({"functions": [fn("<main>", [SRC, st(["unserialize", "(", "$x"], uses=["x"], calls=["unserialize"])], dfg=[(0, 1)])]})
    assert (0, 1) in pairs(d[SEM_POS].edge_index) and (0, 1) in pairs(d[CAND].edge_index)


def test_extract_source_array_vs_plain_array():
    # extract($_POST): source và sink cùng statement -> cờ direct_source_sink (không có cặp i != j)
    d = build({"functions": [fn("<main>", [st(["extract", "(", "$_POST"], uses=["_POST"], calls=["extract"])])]})
    assert d[STMT].x[0, NODE_FEAT_DIM - N_NUMERIC - 1] == 1.0 and int(d[STMT].role[0]) == ROLE_ID["sink"]
    # $d = $_POST; extract($d): chỉ là ỨNG VIÊN (không mô hình spreader, không nâng nhãn)
    d2 = build({"functions": [fn("<main>", [st(["$d", "=", "$_POST"], defs=["d"], uses=["_POST"]),
                                            st(["extract", "(", "$d"], uses=["d"], calls=["extract"])], dfg=[(0, 1)])]})
    assert (0, 1) in pairs(d2[CAND].edge_index)
    assert (0, 1) not in pairs(d2[SEM_POS].edge_index) and (0, 1) not in pairs(d2[SEM_NEG].edge_index)
    # source khác tới extract($_POST) (sink chặt) -> nhãn
    d3 = build({"functions": [fn("<main>", [SRC, st(["extract", "(", "$_GET"], uses=["_GET"], calls=["extract"])])]})
    assert (0, 1) in pairs(d3[SEM_POS].edge_index)


def test_ob_start_variable_callback_is_candidate_only():
    d = build({"functions": [fn("<main>", [st(["$cb", "=", "$_GET", "c"], defs=["cb"], uses=["_GET"]),
                                           st(["ob_start", "(", "$cb"], uses=["cb"], calls=["ob_start"])], dfg=[(0, 1)])]})
    assert (0, 1) in pairs(d[CAND].edge_index) and (0, 1) not in pairs(d[SEM_POS].edge_index)
    assert int(d[STMT].role[1]) == ROLE_ID["cand_sink"]



# ------------------------------------------------------------------ luật CALL NODE cho mọi sink
@pytest.mark.parametrize("stmt,roles", [
    ({"tokens": ["$f", "=", "assert"]}, set()),                                  # literal: $f = 'assert'
    ({"tokens": ["eval"]}, set()),                                               # echo 'eval' (dump AST)
    ({"tokens": ["eval", "$c"], "constructs": ["eval"]}, {"sink"}),              # construct eval
    ({"tokens": ["include", "$p"], "constructs": ["include"]}, {"sink"}),        # include $p; (không ngoặc)
    ({"tokens": ["require", "$f"], "constructs": ["require"]}, {"sink"}),        # require $f;
    ({"tokens": ["require", "a.php"], "constructs": ["require"]}, set()),        # tĩnh -> không
    ({"tokens": ["system", "(", "ls"], "calls": ["system"]}, {"sink"}),
    ({"tokens": ["echo", "system", "$x"]}, set()),                               # tên sink trong text
    ({"tokens": ["<dyncall>", "$f", "(", "$x"], "calls": ["<dyncall>"]}, {"sink"}),   # biến-hàm $f()
    ({"tokens": ["<dyncall>", "$f", "(", "$x"],
      "callargs": [{"name": "<dyncall>", "args": [["x"]]}]}, {"sink"}),           # call node qua callargs
    ({"tokens": ["$o", "=", "shell_exec"], "constructs": ["shell_exec"]}, {"sink"}),   # backtick
    ({"tokens": ["$x", "=", "fwrite"]}, set()),                                  # ứng viên cũng theo luật
])
def test_call_node_law_all_sinks(stmt, roles):
    from hipag.graph.taint_seeds import stmt_roles
    assert stmt_roles(stmt) == roles


@pytest.mark.skipif(not shutil.which("php") or not (ROOT / "vendor/autoload.php").exists(),
                    reason="cần php + vendor (nikic/php-parser)")
@pytest.mark.parametrize("broken", [False, True])
def test_call_node_law_from_real_dumper(tmp_path, broken):
    """Dump thật (nhánh AST và nhánh fallback_tokens khi parse hỏng): literal không là sink; include không ngoặc là sink."""
    from hipag.graph.taint_seeds import stmt_roles
    from hipag.parsing.php_ast import dump_ast
    f = tmp_path / "c.php"
    body = "$f = 'assert'; $f($_POST['x']); include $p; system('ls'); echo 'eval'; $o = `id`; eval($c);"
    f.write_text("<?php\n" + body + (" class {" if broken else "") + "\n")
    d = dump_ast(str(f))
    assert d["status"] == ("fallback_tokens" if broken else "ok")
    got = [(s["tokens"][:3], stmt_roles(s)) for s in d["functions"][0]["stmts"] if s["tokens"]]
    sinks = [t for t, r in got if "sink" in r]
    nonsinks = [t for t, r in got if "sink" not in r]
    assert any(t[0] == "<dyncall>" for t in sinks) and any(t[0] == "include" for t in sinks)
    assert any(t[0] == "system" for t in sinks) and any(t[-1] == "shell_exec" or "shell_exec" in t for t in sinks)
    assert any(t[0] == "eval" and len(t) > 1 for t in sinks)                 # eval($c) là sink
    assert ["$f", "=", "assert"] in nonsinks                                 # $f = 'assert' KHÔNG là sink
    assert any("eval" in t and "$c" not in t for t in nonsinks)              # echo 'eval' KHÔNG là sink
