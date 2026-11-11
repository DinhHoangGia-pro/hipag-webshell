"""Chuẩn hoá đầu vào (tools/php/canon_lib.php): model + probe không thấy comment/docblock/thẻ đóng cuối."""
import base64
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("php") is None or not (ROOT / "vendor").exists(),
                                reason="cần php + vendor/nikic")

SRC = ('<?php\r\n/**\r\n * Docblock @param x\r\n */\r\nfunction f($a) { // tail\r\n    # hash line\r\n'
       '    /* block */\r\n    $s = "keep // not /* x */";\r\n    $h = <<<EOT\r\nl1 # not comment\r\nEOT;\r\n'
       '    return $a . $s . strlen($h);\r\n}\r\necho f("A");\r\n?>\r\n\r\n')


def _canon(tmp_path, src: str) -> str:
    p = tmp_path / "t.php"
    p.write_bytes(src.encode())
    from hipag.parsing.php_ast import canonicalize_batch
    return base64.b64decode(canonicalize_batch([p])[0]).decode()


def test_strips_comments_keeps_strings(tmp_path):
    c = _canon(tmp_path, SRC)
    assert "Docblock" not in c and "tail" not in c and "hash line" not in c and "block */" not in c
    assert '"keep // not /* x */"' in c and "l1 # not comment" in c
    assert "?>" not in c


def test_semantics_preserved(tmp_path):
    c = _canon(tmp_path, SRC)
    a, b = tmp_path / "a.php", tmp_path / "b.php"
    a.write_bytes(SRC.encode()); b.write_bytes(c.encode())
    run = lambda p: subprocess.run(["php", str(p)], capture_output=True).stdout  # noqa: E731
    # Khác biệt DUY NHẤT được phép: khoảng trắng HTML sau thẻ đóng cuối file không còn được in ra.
    assert run(a).rstrip() == run(b).rstrip() and run(a).startswith(b"Akeep")


def test_trailing_close_tag_is_implicit_semicolon(tmp_path):
    # thẻ đóng cuối = ';' ngầm: bỏ thẻ phải thêm ';' (hồi quy: 41 webshell parse lỗi ở lần chạy đầu v6)
    c = _canon(tmp_path, "<?php $a=1;$b=$a+1?>\n")
    p = tmp_path / "c.php"
    p.write_text(c)
    assert subprocess.run(["php", "-l", str(p)], capture_output=True).returncode == 0
    assert "?>" not in c and c.rstrip().endswith(";")


def test_mid_file_close_tag_kept(tmp_path):
    c = _canon(tmp_path, "<?php echo 1; ?>\n<html>tail</html>\n")
    assert "?>" in c and "<html>tail</html>" in c


def test_graph_text_has_no_comments(tmp_path):
    p = tmp_path / "w.php"
    p.write_bytes(SRC.encode())
    from hipag.parsing.php_ast import dump_ast, source_text_of
    d = dump_ast(str(p))
    texts = [s["text"] for fn in d["functions"] for s in fn["stmts"]]
    assert texts and not any("tail" in t or "hash line" in t or "block */" in t for t in texts)
    st = source_text_of(d, str(p))
    assert "Docblock" not in st and "?>" not in st
