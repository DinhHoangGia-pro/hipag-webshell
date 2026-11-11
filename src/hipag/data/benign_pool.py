"""Benign foil KHÓ (configs/dataset/collect.yaml: benign_pool) — dùng bởi scripts/dataset/02_collect_benign.py.

Quy trình (tái lập: seed + commit ghim + sort):
  1. Quét pool ứng viên TRONG RAM: tarball GitHub ghim commit, White.zip (trừ 2000 file đã ở holdout), nguồn v4 trên đĩa.
     Mỗi file: lọc PHP (php_filter), size, entropy byte, cờ hard (hard_regex), cờ backdoor (backdoor_regex).
  2. Loại: backdoor kinh điển (-> benign_backdoor_review.csv), trùng byte với webshell, trùng byte trong pool.
  3. Trọng số ghép phân phối THÔ với webshell train_pool trên lưới (log10 size, entropy):
        w = max((p_ws/p_pool)^power, w_floor) * hard_boost^hard
     Lấy mẫu có trọng số không hoàn lại (Efraimidis–Spirakis), cap theo nguồn, tới n_target.
  4. Chỉ giải nén file được chọn; một phần nhỏ thành biến thể minified (php -w) / packed (eval(gzinflate(base64))).
Lỗi ghi file -> dừng ngay, in thao tác + errno + đường dẫn (ổ ntfs-3g).
"""
from __future__ import annotations

import csv
import errno as errno_mod
import hashlib
import math
import random
import re
import subprocess
import sys
import tarfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from .pipeline import REPO as ROOT
from .pipeline import iter_php_files, rel, sha1_bytes


def entropy(b: bytes) -> float:
    n = len(b)
    if not n:
        return 0.0
    return -sum(c / n * math.log2(c / n) for c in Counter(b).values())


def die_write(op: str, e: OSError):
    print("\n=== LỖI GHI FILE — DỪNG ===", flush=True)
    print(f"thao tác : {op}")
    print(f"errno    : {e.errno} ({errno_mod.errorcode.get(e.errno, '?')}) — {e.strerror}")
    print(f"exception: {e!r}")
    print(f"file ghi : {e.filename}", flush=True)
    raise SystemExit(3)


def safe_write(path: Path, data: bytes):
    op = f"mkdir {path.parent}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        op = f"open('{path}','wb').write({len(data)} bytes)"
        with open(path, "wb") as f:
            f.write(data)
    except OSError as e:
        die_write(op, e)


def _is_php(name: str, data: bytes, filt: dict) -> str | None:
    """None nếu hợp lệ, ngược lại lý do loại (cùng luật iter_php_files)."""
    if len(data) < filt.get("min_bytes", 1):
        return "too_small"
    if len(data) > filt.get("max_bytes", 5_000_000):
        return "too_large"
    if filt.get("require_open_tag", True) and b"<?" not in data:
        return "no_php_open_tag"
    return None


def _php_ext(name: str, filt: dict) -> bool:
    exts = {e.lower() for e in filt.get("extensions", ["php"])}
    return Path(name).suffix.lower().lstrip(".") in exts


def _skip(name: str, filt: dict) -> bool:
    skip = set(filt.get("skip_dirs", []))
    return any(p in skip for p in Path(name).parts[:-1])


def _record(src: str, axis: str, kind: str, archive: str, member: str, data: bytes, rx_hard, rx_bd) -> dict:
    txt = data.decode("utf-8", "replace")
    mh, mb = rx_hard.search(txt), rx_bd.search(txt)
    return {"source": src, "axis": axis, "kind": kind, "archive": archive, "member": member,
            "size": len(data), "raw_sha1": sha1_bytes(data), "log10_size": math.log10(max(len(data), 1)),
            "entropy": entropy(data), "hard": int(bool(mh)), "hard_reason": mh.group(0).strip()[:40] if mh else "",
            "backdoor": int(bool(mb)), "backdoor_match": mb.group(0)[:80] if mb else ""}


def _scan_white(pool, excl, wz, filt, rx_hard, rx_bd):
    z = zipfile.ZipFile(ROOT / wz["zip"])
    names = sorted(n for n in z.namelist() if n.startswith(wz["prefix"]) and n.lower().endswith(".php")
                   and not n.endswith("/"))
    held = set(random.Random(wz["holdout_pick_seed"]).sample(names, wz["holdout_n"]))
    n0 = len(pool)
    for n in names:
        if n in held:
            continue
        data = z.read(n)
        why = _is_php(n, data, filt)
        if why:
            excl.append({"source": wz["name"], "path": f"{wz['zip']}::{n}", "reason": why}); continue
        pool.append(_record(wz["name"], wz["axis"], "zip", wz["zip"], n, data, rx_hard, rx_bd))
    print(f"  pool {wz['name']:16s} {len(pool) - n0:6d} php  (White.zip trừ {len(held)} file holdout)", flush=True)



def scan_pool(pc: dict, filt: dict, rx_hard, rx_bd) -> tuple[list[dict], list[dict]]:
    pool, excl = [], []
    with open(ROOT / pc["sources_tsv"]) as f:
        srcs = [ln.rstrip("\n").split("\t") for ln in f if ln.strip()]
    for row in srcs:
        name, repo, commit, axis = row[:4]
        inc = re.compile(row[4]) if len(row) > 4 and row[4] else None   # chỉ lấy thư mục dữ liệu (theo bản chất)
        tp = ROOT / pc["dl_dir"] / f"{name}.tar.gz"
        n0 = len(pool)
        with tarfile.open(tp, "r:gz") as tf:
            for m in tf:
                if not m.isfile() or not _php_ext(m.name, filt) or _skip(m.name, filt):
                    continue
                if inc is not None and not inc.search(m.name):
                    continue
                data = tf.extractfile(m).read()
                why = _is_php(m.name, data, filt)
                if why:
                    excl.append({"source": name, "path": f"{rel(tp)}::{m.name}", "reason": why}); continue
                pool.append(_record(name, axis, "tar", rel(tp), m.name, data, rx_hard, rx_bd))
        print(f"  pool {name:16s} {len(pool) - n0:6d} php  ({repo}@{commit[:10]})", flush=True)

    wz = pc["white_zip"]
    if wz.get("enabled", True):
        _scan_white(pool, excl, wz, filt, rx_hard, rx_bd)
    else:
        print(f"  pool {wz['name']:16s}      0 php  (TẮT: c01dsnap chỉ dùng cho holdout)", flush=True)
    for s in pc["existing"]:
        n0 = len(pool)
        for p, why in iter_php_files(ROOT / s["path"], filt):
            if why:
                excl.append({"source": s["name"], "path": rel(p), "reason": why}); continue
            pool.append(_record(s["name"], s["axis"], "disk", "", rel(p), p.read_bytes(), rx_hard, rx_bd))
        print(f"  pool {s['name']:16s} {len(pool) - n0:6d} php  (đĩa, cap {s['cap']})", flush=True)
    return pool, excl


def _bin(r: dict, b: dict) -> tuple[int, int]:
    return (int(r["log10_size"] // b["log10_size_step"]), int(r["entropy"] // b["entropy_step"]))


def select(pool: list[dict], ws_feats: list[dict], pc: dict) -> tuple[list[dict], dict]:
    b = pc["bins"]
    ws_c = Counter(_bin(r, b) for r in ws_feats)
    pl_c = Counter(_bin(r, b) for r in pool)
    nws, npl = sum(ws_c.values()), sum(pl_c.values())
    caps = {s["name"]: s["cap"] for s in pc["existing"]}
    caps[pc["white_zip"]["name"]] = pc.get("white_cap", 0)
    caps.update(pc.get("source_caps", {}))
    rng = random.Random(pc["seed"])
    keyed = []
    for r in pool:
        k = _bin(r, b)
        ratio = (ws_c[k] / nws) / (pl_c[k] / npl)
        w = max(ratio ** pc["density_power"], pc["w_floor"]) if ratio > 0 else pc["w_floor"]
        w *= pc["hard_boost"] ** r["hard"]
        r["weight"] = round(w, 4)
        keyed.append((rng.random() ** (1.0 / w), r))
    keyed.sort(key=lambda t: -t[0])
    taken, per = [], Counter()
    for _, r in keyed:
        if len(taken) >= pc["n_target"]:
            break
        if per[r["source"]] >= caps.get(r["source"], pc["per_source_cap"]):
            continue
        per[r["source"]] += 1
        taken.append(r)
    info = {"bins_ws": {f"{k}": v for k, v in sorted(ws_c.items())}, "n_ws_ref": nws, "n_pool": npl}
    return taken, info


def _dest(pc: dict, r: dict) -> Path:
    h = hashlib.sha1(f"{r['archive']}::{r['member']}".encode()).hexdigest()
    base = re.sub(r"[^A-Za-z0-9._-]", "_", Path(r["member"]).name)[-80:]
    return ROOT / pc["extract_dir"] / r["source"] / h[:2] / f"{h[:12]}_{base}"


def extract(sel: list[dict], pc: dict) -> None:
    """Ghi file được chọn (tar/zip) ra đĩa; nguồn 'disk' giữ nguyên đường dẫn."""
    by_arc = defaultdict(dict)
    for r in sel:
        if r["kind"] == "disk":
            r["path"] = r["member"]
        else:
            by_arc[(r["kind"], r["archive"])][r["member"]] = r
    for (kind, arc), want in by_arc.items():
        if kind == "tar":
            with tarfile.open(ROOT / arc, "r:gz") as tf:
                for m in tf:
                    if m.name in want:
                        r = want[m.name]; d = _dest(pc, r)
                        if not d.exists():
                            safe_write(d, tf.extractfile(m).read())
                        r["path"] = rel(d)
        else:
            z = zipfile.ZipFile(ROOT / arc)
            for mem, r in want.items():
                d = _dest(pc, r)
                if not d.exists():
                    safe_write(d, z.read(mem))
                r["path"] = rel(d)


def make_variants(sel: list[dict], pc: dict) -> Counter:
    """minify (php -w) / pack (obfuscate.php L3) cho một phần nhỏ; cập nhật path/size/sha1/variant."""
    rng = random.Random(f"{pc['seed']}:variants")
    idx = list(range(len(sel)))
    rng.shuffle(idx)
    n_min, n_pack = round(pc["minify_frac"] * len(sel)), round(pc["pack_frac"] * len(sel))
    plan = {i: "minified" for i in idx[:n_min]}
    plan.update({i: "packed" for i in idx[n_min:n_min + n_pack]})
    out = Counter()
    vdir = ROOT / pc["extract_dir"] / "_variants"
    pack_jobs = []
    for i, r in enumerate(sel):
        r["variant"] = "original"
        v = plan.get(i)
        if not v:
            continue
        src = ROOT / r["path"]
        h = hashlib.sha1(r["path"].encode()).hexdigest()
        d = vdir / v / h[:2] / f"{h[:12]}.php"
        if v == "minified":
            p = subprocess.run(["php", "-d", "short_open_tag=1", "-w", str(src)], capture_output=True)
            if p.returncode != 0 or not p.stdout.strip():
                continue
            safe_write(d, p.stdout)
        else:
            pack_jobs.append((r, src, d))
            continue
        r["path"], r["variant"] = rel(d), v
        out[v] += 1
    if pack_jobs:
        try:
            for _, _, d in pack_jobs:
                d.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            die_write(f"mkdir {d.parent}", e)
        inp = "".join(f"L3\t{s}\t{d}\n" for _, s, d in pack_jobs)
        p = subprocess.run(["php", "-d", "short_open_tag=1", str(ROOT / "tools/php/obfuscate.php")],
                           input=inp, capture_output=True, text=True)
        import json
        res = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
        for (r, _, d), x in zip(pack_jobs, res):
            if x.get("ok") and d.exists():
                r["path"], r["variant"] = rel(d), "packed"
                out["packed"] += 1
            elif not x.get("ok") and "space" in str(x.get("error", "")).lower():
                print(f"\n=== LỖI GHI FILE (obfuscate.php) — DỪNG ===\nfile ghi : {d}\nlỗi: {x.get('error')}")
                raise SystemExit(3)
    for r in sel:
        if r["variant"] != "original":
            data = (ROOT / r["path"]).read_bytes()
            r["size"], r["raw_sha1"] = len(data), sha1_bytes(data)
    return out


def write_pool_csv(path: Path, pool: list[dict], sel_ids: set) -> None:
    fields = ["source", "axis", "kind", "archive", "member", "size", "raw_sha1", "log10_size", "entropy", "hard",
              "hard_reason", "backdoor", "backdoor_match", "weight", "excluded", "selected"]
    try:
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in pool:
                w.writerow({**r, "selected": int(id(r) in sel_ids)})
    except OSError as e:
        die_write(f"write {path}", e)


def log(msg):
    print(msg, file=sys.stdout, flush=True)
