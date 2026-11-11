"""UPG-02 — giải vỏ TĨNH (tools/php/deobf_lib.php + dump_ast.php): constant-fold decoder trên literal, parse kết quả
như PHP, ghép AST khôi phục vào đồ thị (cờ deobfuscated). KHÔNG execute. Dump thật trên file PHP tí hon + IR giả."""
import base64
import binascii
import codecs
import gzip
import os
import shutil
import time
import urllib.parse
import zlib
from pathlib import Path

import pytest

from hipag.data.build import STAT_FIELDS, esem_stats
from hipag.graph.edges import SEM_POS, STMT
from hipag.graph.hierarchical_graph import build_hetero_from_ir
from hipag.graph.node_features import N_NUMERIC, NODE_FEAT_DIM

ROOT = Path(__file__).resolve().parents[1]
needs_php = pytest.mark.skipif(not shutil.which("php") or not (ROOT / "vendor/autoload.php").exists(),
                               reason="cần php + vendor (nikic/php-parser)")
MAL = b"$c = $_POST['c']; eval($c);"                 # payload: đọc $_POST rồi eval
BENIGN = b'$a = strlen("hi"); echo $a;'
b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
pairs = lambda ei: set(map(tuple, ei.t().tolist()))  # noqa: E731


def raw_deflate(b):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(b) + c.flush()


def dump(tmp_path, body, name="t.php"):
    from hipag.parsing.php_ast import ast_to_ir, dump_ast
    f = tmp_path / name
    f.write_text("<?php\n" + body + "\n")
    d = dump_ast(str(f))
    return d, build_hetero_from_ir(ast_to_ir(d, f.read_text()), label=1)


def deobf_rows(g):
    """[(role, is_deobf)] mỗi statement."""
    return list(zip(g[STMT].role.tolist(), g[STMT].deobf.tolist()))


# ------------------------------------------------------------------ 5 ca trong spec
@needs_php
def test_eval_base64_reveals_post_to_eval(tmp_path):
    d, g = dump(tmp_path, f"eval(base64_decode('{b64(MAL)}'));\necho 1;")
    assert d["deobf"]["folded"] == 1 and d["deobf"]["grafted"] == 1
    deob = [i for i, x in enumerate(g[STMT].deobf.tolist()) if x]
    roles = g[STMT].role.tolist()
    src = [i for i in deob if roles[i] == 1]
    snk = [i for i in deob if roles[i] == 2]
    assert src and snk and any((i, j) in pairs(g[SEM_POS].edge_index) for i in src for j in snk)
    assert int(g.n_deobf_stmts) == 2 and int(g.n_deobf_grafted) == 1


@needs_php
def test_gzinflate_base64_benign_folds_without_taint(tmp_path):
    d, g = dump(tmp_path, f"eval(gzinflate(base64_decode('{b64(raw_deflate(BENIGN))}')));")
    assert d["deobf"]["grafted"] == 1 and int(g.n_deobf_stmts) >= 1
    assert g[SEM_POS].edge_index.shape[1] == 0
    assert not any(r == 1 for r, _ in deobf_rows(g))                  # không có source


@needs_php
def test_dynamic_argument_not_folded(tmp_path):
    d, g = dump(tmp_path, "eval(base64_decode($_POST['x']));")
    assert d["deobf"]["folded"] == 0 and d["deobf"]["grafted"] == 0 and d["deobf"]["not_literal"] == 1
    assert int(g.n_deobf_stmts) == 0
    assert g[STMT].x[0, NODE_FEAT_DIM - N_NUMERIC - 1] == 1.0          # luồng source->sink vốn đã thấy (direct)


@needs_php
def test_png_blob_is_data_not_code(tmp_path):
    png = b"\x89PNG\r\n\x1a\n" + os.urandom(256)
    d, g = dump(tmp_path, f"$img = base64_decode('{b64(png)}');\necho $img;")
    assert d["deobf"]["folded"] == 1 and d["deobf"]["grafted"] == 0
    assert d["deobf"]["skipped"] == {"not_php": 1}
    assert int(g.n_deobf_stmts) == 0


def _nested(n, payload=MAL):
    lit = payload
    for _ in range(n):
        lit = base64.b64encode(lit)
    return "base64_decode(" * n + "'" + lit.decode() + "'" + ")" * n


@needs_php
def test_nesting_depth_limit(tmp_path):
    d5, g5 = dump(tmp_path, f"eval({_nested(5)});", "n5.php")
    assert d5["deobf"]["grafted"] == 1 and int(g5.n_deobf_stmts) == 2           # 5 lớp: OK
    d6, g6 = dump(tmp_path, f"eval({_nested(6)});", "n6.php")
    assert d6["deobf"]["skipped"] == {"too_deep": 1} and d6["deobf"]["grafted"] == 0
    assert d6["deobf"]["folded"] == 0 and int(g6.n_deobf_stmts) == 0           # không fold lại từng phần
    assert any(e["reason"] == "too_deep" for e in d6["deobf"]["events"])       # có log


@needs_php
def test_decompression_bomb_skipped_safely(tmp_path):
    bomb = raw_deflate(b"A" * 6_000_000)                                        # ~6KB nén -> 6MB
    t0 = time.time()
    d, g = dump(tmp_path, f"eval(gzinflate(base64_decode('{b64(bomb)}')));")
    assert time.time() - t0 < 30
    assert d["deobf"]["skipped"] == {"too_big": 1} and d["deobf"]["grafted"] == 0
    assert int(g.n_deobf_skipped) == 1 and int(g.n_deobf_stmts) == 0


# ------------------------------------------------------------------ mở rộng
@needs_php
@pytest.mark.parametrize("name,enc", [
    ("str_rot13", lambda b: codecs.encode(b.decode(), "rot13")),
    ("hex2bin", lambda b: b.hex()),
    ("urldecode", lambda b: urllib.parse.quote(b.decode(), safe="")),
    ("strrev", lambda b: b.decode()[::-1]),
    ("gzuncompress", None), ("gzdecode", None), ("convert_uudecode", None),
])
def test_each_decoder(tmp_path, name, enc):
    if name in ("gzuncompress", "gzdecode"):
        blob = zlib.compress(MAL) if name == "gzuncompress" else gzip.compress(MAL)
        expr = f"{name}(base64_decode('{b64(blob)}'))"
    elif name == "convert_uudecode":
        uu = b"".join(binascii.b2a_uu(MAL[i:i + 45], backtick=True) for i in range(0, len(MAL), 45)) + b"`\n"
        expr = f"{name}(base64_decode('{b64(uu)}'))"
    else:
        lit = enc(MAL).replace("\\", "\\\\").replace("'", "\\'")
        expr = f"{name}('{lit}')"
    d, g = dump(tmp_path, f"eval({expr});")
    assert d["deobf"]["grafted"] == 1, d["deobf"]
    assert any(r == 1 and dob for r, dob in deobf_rows(g)) and any(r == 2 and dob for r, dob in deobf_rows(g))


@needs_php
def test_multistage_eval_grafts_recursively_with_limit(tmp_path):
    def stages(k):
        code = MAL
        for _ in range(k):
            code = b"eval(base64_decode('" + base64.b64encode(code) + b"'));"
        return code.decode()
    d2, g2 = dump(tmp_path, stages(2), "s2.php")
    assert d2["deobf"]["grafted"] == 2 and g2[SEM_POS].edge_index.shape[1] >= 1
    d7, _ = dump(tmp_path, stages(7), "s7.php")
    assert d7["deobf"]["grafted"] == 5 and d7["deobf"]["skipped"] == {"graft_too_deep": 1}


@needs_php
def test_literal_concat_and_assignment_then_eval(tmp_path):
    enc = b64(MAL)
    k = len(enc) // 2
    d, g = dump(tmp_path, f"$x = base64_decode('{enc[:k]}' . '{enc[k:]}');\neval($x);")
    assert d["deobf"]["grafted"] == 1                         # phép nối literal cũng là hằng
    assert any(r == 1 and dob for r, dob in deobf_rows(g))


@needs_php
def test_decoded_code_is_never_executed(tmp_path):
    marker = tmp_path / "PWNED"
    payload = f"file_put_contents('{marker}', 'x'); system('touch {marker}2');".encode()
    d, g = dump(tmp_path, f"eval(base64_decode('{b64(payload)}'));")
    assert d["deobf"]["grafted"] == 1 and int(g.n_deobf_stmts) == 2   # đã parse + ghép...
    assert not marker.exists() and not Path(str(marker) + "2").exists()   # ...nhưng KHÔNG chạy


def test_deobf_lib_has_no_execution_primitives():
    src = (ROOT / "tools/php/deobf_lib.php").read_text()
    code = "\n".join(ln.split("//")[0] for ln in src.splitlines())   # bỏ comment
    for bad in ("eval(", "assert(", "include", "require", "create_function", "call_user_func", "system(",
                "exec(", "passthru(", "proc_open(", "popen(", "`"):
        assert bad not in code, bad
    import re
    assert not re.search(r"\$\w+\s*\(", code), "không được gọi hàm theo tên động"


# ------------------------------------------------------------------ IR giả (builder)
def test_builder_carries_deobf_flag_synthetic():
    st = lambda toks, **k: {"kind": "Expression", "text": " ".join(toks), "tokens": toks, **k}  # noqa: E731
    ir = {"functions": [{"name": "<main>", "stmts": [
        st(["eval", "base64_decode", "(", "<str>"], constructs=["eval"], calls=["base64_decode"]),
        st(["$c", "=", "$_POST", "c"], defs=["c"], uses=["_POST"], deobfuscated=True),
        st(["eval", "$c"], uses=["c"], constructs=["eval"], deobfuscated=True)],
        "cfg": [(0, 1), (1, 2)], "dfg": [(1, 2)]}],
        "deobf": {"folded": 1, "grafted": 1, "skipped": {"not_php": 2}}}
    g = build_hetero_from_ir(ir, label=1)
    assert g[STMT].deobf.tolist() == [False, True, True]
    assert (1, 2) in pairs(g[SEM_POS].edge_index)
    s = esem_stats(g)
    assert (s["n_deobf_stmts"], s["n_deobf_folded"], s["n_deobf_grafted"], s["n_deobf_skipped"]) == (2, 1, 1, 2)
    assert {"n_deobf_folded", "n_deobf_grafted", "n_deobf_skipped", "n_deobf_stmts", "deobf_skip_reasons"} \
        <= set(STAT_FIELDS)
    g0 = build_hetero_from_ir({"functions": [{"name": "<main>", "stmts": [st(["echo"])]}]}, label=0)
    assert g0[STMT].deobf.tolist() == [False] and int(g0.n_deobf_stmts) == 0   # IR cũ không có cờ


# ------------------------------------------------------------------ const-propagation HẸP
B64_MAL = b64(MAL)


@needs_php
@pytest.mark.parametrize("body", [
    f"$k = '{B64_MAL}';\neval(base64_decode($k));",
    f"$k = '{B64_MAL[:20]}' . '{B64_MAL[20:]}';\neval(base64_decode($k));",                # gán từ nối literal
    f"function f() {{ $k = '{B64_MAL}'; eval(base64_decode($k)); }}",                       # scope hàm
])
def test_const_prop_reveals_taint(tmp_path, body):
    d, g = dump(tmp_path, body)
    assert d["deobf"]["const_folds"] == 1 and d["deobf"]["grafted"] == 1
    roles = g[STMT].role.tolist()
    deob = [i for i, x in enumerate(g[STMT].deobf.tolist()) if x]
    assert any((i, j) in pairs(g[SEM_POS].edge_index) for i in deob if roles[i] == 1 for j in deob if roles[j] == 2)


@needs_php
@pytest.mark.parametrize("case,body", [
    ("assigned_twice", f"$k = '{B64_MAL}';\n$k = 'eA==';\neval(base64_decode($k));"),
    ("append", f"$k = '{B64_MAL}';\n$k .= '';\neval(base64_decode($k));"),
    ("from_post", "$k = $_POST['k'];\neval(base64_decode($k));"),                          # đối số động thật
    ("superglobal", "eval(base64_decode($_COOKIE));"),
    ("use_before_assign", f"eval(base64_decode($k));\n$k = '{B64_MAL}';"),
    ("extract_in_scope", f"$k = '{B64_MAL}';\nextract($_GET);\neval(base64_decode($k));"),
    ("varvar_in_scope", f"$k = '{B64_MAL}';\n$$n = 1;\neval(base64_decode($k));"),
    ("by_ref_arg", f"$k = '{B64_MAL}';\npreg_match('/x/', 'y', $k);\neval(base64_decode($k));"),
    ("array_write", f"$k = '{B64_MAL}';\n$k[0] = 'x';\neval(base64_decode($k));"),
    ("foreach_var", f"$k = '{B64_MAL}';\nforeach ($a as $k) {{}}\neval(base64_decode($k));"),
    ("other_scope", f"$k = '{B64_MAL}';\nfunction f() {{ eval(base64_decode($k)); }}"),
    ("param", f"function f($k) {{ $k = '{B64_MAL}'; eval(base64_decode($k)); }}"),
])
def test_const_prop_not_folded(tmp_path, case, body):
    d, g = dump(tmp_path, body)
    assert d["deobf"]["folded"] == 0 and d["deobf"]["grafted"] == 0, (case, d["deobf"])
    assert int(g.n_deobf_stmts) == 0


# ------------------------------------------------------------------ toggle deobf on/off (ablation no_deobf)
@needs_php
def test_toggle_off_graph_as_before(tmp_path):
    from hipag.parsing.php_ast import ast_to_ir, dump_ast
    f = tmp_path / "t.php"
    f.write_text(f"<?php\n$k = '{B64_MAL}';\neval(base64_decode($k));\neval(base64_decode('{B64_MAL}'));\necho 1;\n")
    on, off = dump_ast(str(f)), dump_ast(str(f), deobf=False)
    assert on["deobf"]["grafted"] == 2 and off["deobf"] == {**off["deobf"], "enabled": False, "folded": 0,
                                                            "grafted": 0}
    strip = lambda d: [(s["kind"], s["tokens"]) for fn in d["functions"] for s in fn["stmts"]  # noqa: E731
                       if not s["deobfuscated"]]
    assert strip(off) == strip(on)                       # tắt = đúng đồ thị gốc, không thêm/bớt gì khác
    g_off = build_hetero_from_ir(ast_to_ir(off, f.read_text()), label=1)
    assert int(g_off.n_deobf_stmts) == 0 and int(g_off.n_deobf_grafted) == 0
    assert g_off[SEM_POS].edge_index.shape[1] == 0       # taint ẩn trong payload: không thấy khi tắt


def test_toggle_config_and_resume_guard():
    from hipag.data.build import check_resume_deobf
    from hipag.utils.config import load_config
    on = load_config(ROOT / "configs/dataset/build_graphs.yaml", root=ROOT)
    off = load_config(ROOT / "configs/dataset/build_graphs_nodeobf.yaml", root=ROOT)
    assert on["parser"]["deobf"] is True and off["parser"]["deobf"] is False
    assert off["parser"]["phpparser_entry"] == on["parser"]["phpparser_entry"]          # kế thừa phần còn lại
    assert off["out_small_dir"] != on["out_small_dir"] and off["out_stats"] != on["out_stats"]
    check_resume_deobf({}, True, "x")                                                    # thư mục trống: OK
    check_resume_deobf({"a": {"deobf": 1}}, True, "x")                                   # cùng chế độ: OK
    with pytest.raises(SystemExit):
        check_resume_deobf({"a": {"deobf": 1}}, False, "x")                              # trộn chế độ
    with pytest.raises(SystemExit):
        check_resume_deobf({"a": {"sample_id": "a"}}, True, "x")                         # log trước UPG-02
