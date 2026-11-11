"""Tiện ích dùng chung cho scripts/dataset/*.py (không phụ thuộc torch)."""
from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def rel(p: str | Path) -> str:
    """Đường dẫn tương đối theo gốc repo (để manifest không chứa đường dẫn tuyệt đối)."""
    return os.path.relpath(Path(p).resolve(), REPO)


def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def sha256_file(p: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while blk := f.read(chunk):
            h.update(blk)
    return h.hexdigest()


def read_csv(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: str | Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0].keys()) if rows else [])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def iter_php_files(root: str | Path, filt: dict):
    """Duyệt `root`, trả (path, None) cho file PHP hợp lệ hoặc (path, lý_do_loại) cho file đuôi PHP bị loại.
    File không có đuôi PHP bị bỏ qua im lặng (ảnh, README, asp...)."""
    exts = {e.lower() for e in filt.get("extensions", ["php"])}
    skip = set(filt.get("skip_dirs", []))
    lo, hi = filt.get("min_bytes", 1), filt.get("max_bytes", 5_000_000)
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in skip)
        for fn in sorted(fns):
            p = Path(dp) / fn
            if p.suffix.lower().lstrip(".") not in exts or p.is_symlink() or not p.is_file():
                continue
            size = p.stat().st_size
            if size < lo:
                yield p, "too_small"; continue
            if size > hi:
                yield p, "too_large"; continue
            if filt.get("require_open_tag", True):
                with open(p, "rb") as f:
                    if b"<?" not in f.read():
                        yield p, "no_php_open_tag"; continue
            yield p, None


MANIFEST_FIELDS = ["sample_id", "label", "source", "year", "role", "path", "ext", "size", "raw_sha1",
                   "hard", "hard_reason", "axis", "variant"]
