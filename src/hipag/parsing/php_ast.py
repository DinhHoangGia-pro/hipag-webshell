"""PHP -> AST (qua nikic/PHP-Parser, chạy ngoài tiến trình). Trả JSON AST đã chuẩn hoá."""
from __future__ import annotations
import json, subprocess
from pathlib import Path


def dump_ast(php_file: str, php_bin: str = "php", entry: str = "tools/php/dump_ast.php") -> dict:
    """Gọi nikic/PHP-Parser, trả dict AST. TODO: xử lý file parse-fail (obfuscation nặng)."""
    out = subprocess.run([php_bin, entry, php_file], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"PHP parse failed: {php_file}\n{out.stderr}")
    return json.loads(out.stdout)
