"""PHP -> IR thô mức statement qua nikic/PHP-Parser (tools/php/dump_ast.php, chạy ngoài tiến trình).

dump_ast(file)          : một file -> dict (xem đầu tools/php/dump_ast.php cho schema).
dump_batch(paths, ...)  : nhiều file, mỗi tiến trình PHP xử lý một chunk; chunk sập/timeout -> chạy lại từng file;
                          file vẫn sập -> status='parser_crash' (graph rỗng 1 nút, KHÔNG loại âm thầm — RQF-05).
ast_to_ir(dump, text)   : dict thô -> IR mà graph.hierarchical_graph.build_hetero_from_ir nhận.
"""
from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .call_include_graph import build_call_include
from .cfg_dfg import build_cfg, build_dfg

REPO = Path(__file__).resolve().parents[3]
DEFAULT_ENTRY = str(REPO / "tools/php/dump_ast.php")
PHP_FLAGS = ["-d", "short_open_tag=1", "-d", "memory_limit=1536M", "-d", "error_reporting=0", "-d", "display_errors=0"]


def _cmd(php_bin: str, entry: str, *args: str) -> list[str]:
    return [php_bin, *PHP_FLAGS, entry, *args]


def _flags(deobf: bool) -> list[str]:
    return [] if deobf else ["--no-deobf"]


def dump_ast(php_file: str, php_bin: str = "php", entry: str = DEFAULT_ENTRY, timeout: float = 120,
             deobf: bool = True) -> dict:
    """Một file -> dict thô. Sập/timeout -> status='parser_crash'. deobf=False -> tắt giải vỏ tĩnh (UPG-02)."""
    try:
        out = subprocess.run(_cmd(php_bin, entry, *_flags(deobf), str(php_file)), capture_output=True, text=True,
                             timeout=timeout)
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout)
        err = (out.stderr or out.stdout)[-300:]
    except subprocess.TimeoutExpired:
        err = f"timeout>{timeout}s"
    return {"path": str(php_file), "status": "parser_crash", "parser": None, "n_errors": 0, "error": err,
            "functions": [], "n_includes": 0, "n_stmt_total": 0, "deobf": {"enabled": deobf}}


def _run_chunk(paths: list[str], php_bin: str, entry: str, timeout: float, deobf: bool = True) -> list[dict]:
    try:
        out = subprocess.run(_cmd(php_bin, entry, *_flags(deobf), "--batch"), input="\n".join(paths) + "\n",
                             capture_output=True, text=True, timeout=timeout * len(paths))
        lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
        if out.returncode == 0 and len(lines) == len(paths):
            res = [json.loads(ln) for ln in lines]
            if all(r.get("path") == p for r, p in zip(res, paths)):
                return res
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return [dump_ast(p, php_bin, entry, timeout, deobf) for p in paths]   # chunk lỗi -> từng file


def dump_batch(paths, php_bin: str = "php", entry: str = DEFAULT_ENTRY, chunk: int = 64,
               workers: int = 8, timeout: float = 60, deobf: bool = True):
    """Sinh (path, dict) theo đúng thứ tự `paths`."""
    paths = [str(p) for p in paths]
    chunks = [paths[i:i + chunk] for i in range(0, len(paths), chunk)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(lambda c: _run_chunk(c, php_bin, entry, timeout, deobf), chunks):
            for r in res:
                yield r["path"], r


def source_text_of(dump: dict, path: str) -> str:
    """source_text cho model = bản CHUẨN HOÁ (canon_lib.php: bỏ comment/docblock/thẻ đóng cuối) mà dump_ast.php
    đã parse — cùng một bản với text node. Dump không có canon_b64 (crash) -> chuẩn hoá riêng; lỗi -> byte thô."""
    import base64
    b64 = dump.get("canon_b64")
    if b64 is None:
        b64 = (canonicalize_batch([path]) or [None])[0]
    data = base64.b64decode(b64) if b64 is not None else Path(path).read_bytes()
    return data.decode("utf-8", "replace")


def canonicalize_batch(paths, php_bin: str = "php", chunk: int = 200, workers: int = 8) -> list[str | None]:
    """Chuẩn hoá hàng loạt (tools/php/canonicalize.php) -> list canon_b64 theo đúng thứ tự (None nếu không đọc được).
    Dùng cho probe để đặc trưng nông đo trên ĐÚNG bản model thấy."""
    paths = [str(p) for p in paths]
    entry = str(REPO / "tools/php/canonicalize.php")

    def run(ch):
        out = subprocess.run([php_bin, *PHP_FLAGS, entry], input="\n".join(ch) + "\n", capture_output=True, text=True)
        res = [json.loads(x) for x in out.stdout.splitlines() if x.strip()]
        if len(res) != len(ch):
            raise RuntimeError(f"canonicalize.php lệch dòng ({len(res)}/{len(ch)}): {out.stderr[-300:]}")
        return [r.get("canon_b64") for r in res]

    chunks = [paths[i:i + chunk] for i in range(0, len(paths), chunk)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return [x for res in ex.map(run, chunks) for x in res]


def ast_to_ir(dump: dict, source_text: str = "") -> dict:
    """dict thô (dump_ast.php) -> IR {functions:[{name,params,stmts,cfg,dfg}], calls, includes, source_text}.
    Statement mang thêm defs/uses/calls/callargs để builder bridge taint liên thủ tục (arg->param).
    Dump cũ / fallback_tokens thiếu params/callargs -> giữ None/[] và builder dùng nhánh fallback có log."""
    funcs = []
    for fn in dump.get("functions") or []:
        stmts = fn.get("stmts", [])
        cfg = build_cfg(fn)
        funcs.append({
            "name": fn.get("name", "?"),
            "params": fn.get("params"),                      # None nếu dump không có (dump cũ / fallback_tokens)
            "stmts": [{"kind": s.get("kind", "Other"), "text": s.get("text", ""), "tokens": s.get("tokens", []),
                       "defs": s.get("defs", []), "uses": s.get("uses", []), "calls": s.get("calls", []),
                       "callargs": s.get("callargs"), "constructs": s.get("constructs", []),
                       "deobfuscated": bool(s.get("deobfuscated", False))}         # UPG-02: ghép từ mã giải vỏ
                      for s in stmts],
            "cfg": cfg,
            "dfg": build_dfg(stmts, cfg),
        })
    calls, includes = build_call_include(dump)
    return {"functions": funcs, "calls": calls, "includes": includes, "source_text": source_text,
            "deobf": dump.get("deobf") or {}}
