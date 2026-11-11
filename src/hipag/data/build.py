"""Dựng đồ thị hàng loạt (dùng chung cho scripts/dataset/04_build_graphs.py và 06_build_obfuscation_matrix.py).

build_chunk chạy trong tiến trình con: dump_batch (1 tiến trình PHP/chunk) -> ast_to_ir -> build_hetero_from_ir
-> torch.save vào <out_small_dir>/<2hex>/<sample_id>.pt (ổ NTFS: tránh >10k file/thư mục).
run_build: song song theo chunk + resume theo log jsonl.
"""
from __future__ import annotations

import errno as errno_mod
import io
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .pipeline import REPO as ROOT

STAT_FIELDS = ["sample_id", "label", "source", "path", "graph_path", "status", "parser", "n_errors", "error",
               "n_stmt_total", "n_stmt", "n_func", "n_seq", "n_cfg", "n_dfg", "n_call", "n_includes",
               "n_cand", "n_cand_full", "cand_capped", "n_sem_pos", "n_sem_neg", "n_role_src", "n_role_sink",
               "graph_bytes",
               # instrumentation E_sem (nhãn chặt / ứng viên nới / bridge liên thủ tục / cap thông minh)
               "has_source", "has_sink", "has_cand_sink", "has_both", "n_rule_pairs", "n_candidate_pairs",
               "n_typed_pairs", "n_typed_cut", "direct_source_sink_count",
               "n_bridged_crossfn", "n_bridged_arg_carried", "n_bridged_fallback",
               "n_bridged_return_exact", "n_bridged_return_fallback",
               # UPG-02 giải vỏ tĩnh
               "n_deobf_folded", "n_deobf_grafted", "n_deobf_skipped", "n_deobf_stmts", "deobf_skip_reasons",
               "deobf"]   # 1/0: đồ thị dựng với giải vỏ tĩnh bật/tắt (parser.deobf)


def check_resume_deobf(done: dict, deobf: bool, out_dir) -> None:
    """Không trộn đồ thị dựng với/không giải vỏ tĩnh trong cùng out_small_dir (ablation no_deobf phải ở thư mục riêng).
    Log cũ không có cột 'deobf' (dựng trước UPG-02) cũng bị từ chối: dumper đã đổi, phải dựng lại."""
    modes = {s.get("deobf") for s in done.values()}
    want = int(bool(deobf))
    if modes and modes != {want}:
        old = "trước UPG-02 (không có cột deobf)" if None in modes else f"deobf={sorted(m for m in modes if m is not None)}"
        raise SystemExit(f"Từ chối resume: {out_dir} đang chứa đồ thị dựng {old}, cấu hình hiện tại deobf={want}. "
                         f"Dùng out_small_dir riêng (vd configs/dataset/build_graphs_nodeobf.yaml) hoặc xoá log + đồ thị cũ.")


def resolve_graph_cfg(cfg: dict) -> dict:
    """Trộn khối `esem:` của config model (cfg['model_config'], mặc định configs/model/hipag_base.yaml) vào
    cfg['graph'] — esem_hop/interproc_depth/max_cand/cross_function đọc từ MỘT nguồn."""
    from hipag.graph.hierarchical_graph import graph_cfg_with_esem
    from hipag.utils.config import load_config
    mpath = ROOT / cfg.get("model_config", "configs/model/hipag_base.yaml")
    return {**cfg, "graph": graph_cfg_with_esem(cfg.get("graph"), load_config(mpath, root=ROOT))}


def esem_stats(d) -> dict:
    """Cột instrumentation E_sem từ một HeteroData đã dựng."""
    from hipag.graph.edges import CAND, SEM_POS
    from hipag.graph.node_features import STMT_KINDS
    x, role = d["stmt"].x, d["stmt"].role
    c = len(STMT_KINDS)
    has_src, has_sink = bool((x[:, c] > 0.5).any()), bool((x[:, c + 1] > 0.5).any())
    g = lambda k: int(getattr(d, k)) if hasattr(d, k) else 0  # noqa: E731
    return {"has_source": int(has_src), "has_sink": int(has_sink), "has_cand_sink": int(bool((role == 4).any())),
            "has_both": int(has_src and has_sink), "n_rule_pairs": d[SEM_POS].edge_index.shape[1],
            "n_candidate_pairs": d[CAND].edge_index.shape[1], "n_typed_pairs": g("n_typed_pairs"),
            "n_typed_cut": g("n_typed_cut"), "direct_source_sink_count": int((x[:, c + 3] > 0.5).sum()),
            "n_bridged_crossfn": g("n_bridged_crossfn"), "n_bridged_arg_carried": g("n_bridged_arg_carried"),
            "n_bridged_fallback": g("n_bridged_fallback"),
            "n_bridged_return_exact": g("n_bridged_return_exact"),
            "n_bridged_return_fallback": g("n_bridged_return_fallback"),
            "n_deobf_folded": g("n_deobf_folded"), "n_deobf_grafted": g("n_deobf_grafted"),
            "n_deobf_skipped": g("n_deobf_skipped"), "n_deobf_stmts": g("n_deobf_stmts")}


def graph_relpath(sample_id: str) -> str:
    return f"{sample_id.rsplit('_', 1)[-1][:2]}/{sample_id}.pt"


def _seed_of(sample_id: str) -> int:
    import zlib
    return zlib.crc32(sample_id.encode()) & 0x7FFFFFFF


def build_chunk(rows: list[dict], cfg: dict) -> tuple[list[dict], dict | None]:
    """Chạy trong tiến trình con: dump_batch (1 tiến trình PHP) -> build_hetero_from_ir -> torch.save."""
    import torch
    torch.set_num_threads(1)
    from hipag.graph.edges import CAND, PYG_EDGE, SEM_NEG, SEM_POS
    from hipag.graph.hierarchical_graph import build_hetero_from_ir
    from hipag.parsing.php_ast import ast_to_ir, dump_batch, source_text_of

    out_dir = ROOT / cfg["out_small_dir"]
    pcfg = cfg["parser"]
    paths = [str(ROOT / r["path"]) for r in rows]
    stats = []
    deobf = bool(pcfg.get("deobf", True))
    dumps = dict(dump_batch(paths, pcfg["php_bin"], str(ROOT / pcfg["phpparser_entry"]), chunk=len(paths),
                            workers=1, timeout=pcfg["timeout_s"], deobf=deobf))
    for r, p in zip(rows, paths):
        dump = dumps[p]
        text = source_text_of(dump, p)          # bản chuẩn hoá (không comment/docblock/thẻ đóng cuối)
        ir = ast_to_ir(dump, text)
        d = build_hetero_from_ir(ir, cfg["graph"], label=int(r["label"]), seed=_seed_of(r["sample_id"]))
        gp = graph_relpath(r["sample_id"])
        # Serialize vào RAM rồi ghi bằng open() thường: OSError mang errno + filename (torch.save thì không).
        buf = io.BytesIO()
        torch.save(d, buf)
        op = f"mkdir(parents=True) {out_dir / gp}.parent"
        try:
            (out_dir / gp).parent.mkdir(parents=True, exist_ok=True)
            op = f"open('{out_dir / gp}', 'wb').write({buf.tell()} bytes)"
            with open(out_dir / gp, "wb") as fh:
                fh.write(buf.getvalue())
        except OSError as e:
            return stats, {"op": op, "errno": e.errno, "errname": errno_mod.errorcode.get(e.errno, "?"),
                           "strerror": e.strerror, "exc": repr(e), "filename": e.filename,
                           "sample_id": r["sample_id"], "source_php": r["path"]}
        role = d["stmt"].role
        stats.append({
            "sample_id": r["sample_id"], "label": r["label"], "source": r["source"], "path": r["path"],
            "graph_path": gp, "status": dump["status"], "parser": dump.get("parser") or "",
            "n_errors": dump.get("n_errors", 0), "error": (dump.get("error") or "").replace("\n", " ")[:200],
            "n_stmt_total": dump.get("n_stmt_total", 0), "n_stmt": int(d["stmt"].num_nodes),
            "n_func": int(d["func"].num_nodes),
            "n_seq": d[PYG_EDGE["E_seq"]].edge_index.shape[1], "n_cfg": d[PYG_EDGE["E_cfg"]].edge_index.shape[1],
            "n_dfg": d[PYG_EDGE["E_dfg"]].edge_index.shape[1], "n_call": d[PYG_EDGE["E_call"]].edge_index.shape[1],
            "n_includes": dump.get("n_includes", 0),
            "n_cand": d[CAND].edge_index.shape[1], "n_cand_full": int(d.n_cand_full),
            "cand_capped": int(d.cand_capped), "n_sem_pos": d[SEM_POS].edge_index.shape[1],
            "n_sem_neg": d[SEM_NEG].edge_index.shape[1],
            "n_role_src": int((role == 1).sum()), "n_role_sink": int((role == 2).sum()),
            "graph_bytes": (out_dir / gp).stat().st_size,
            **esem_stats(d),
            "deobf_skip_reasons": "|".join(f"{k}:{v}" for k, v in sorted(((dump.get("deobf") or {})
                                                                         .get("skipped") or {}).items())),
            "deobf": int(deobf),
        })
    return stats, None


def run_build(rows: list[dict], cfg: dict, log_path: Path, label: str = "build") -> list[dict]:
    """Dựng đồ thị cho `rows` (cần sample_id, label, source, path), resume theo log jsonl."""
    cfg = resolve_graph_cfg(cfg)
    t = cfg["graph"]["taint"]
    print(f"[{label}] E_sem: esem_hop={t['max_hops']} interproc_depth={t['interproc_depth']} "
          f"max_cand={t['max_cand']} cross_function={t['cross_function']}", flush=True)
    out_dir = ROOT / cfg["out_small_dir"]
    done = {}
    if log_path.exists():
        for ln in log_path.read_text().splitlines():
            if ln.strip():
                s = json.loads(ln)
                done[s["sample_id"]] = s
    deobf = bool(cfg["parser"].get("deobf", True))
    print(f"[{label}] giải vỏ tĩnh (UPG-02): {'BẬT' if deobf else 'TẮT (ablation no_deobf)'}", flush=True)
    check_resume_deobf(done, deobf, out_dir)
    todo = [r for r in rows if not (r["sample_id"] in done and (out_dir / done[r["sample_id"]]["graph_path"]).exists())]
    print(f"[{label}] tổng {len(rows)}; đã có {len(rows) - len(todo)}; cần dựng {len(todo)}", flush=True)
    ch = cfg.get("chunk", 32)
    chunks = [todo[i:i + ch] for i in range(0, len(todo), ch)]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with ProcessPoolExecutor(cfg.get("workers", 8)) as ex, open(log_path, "a") as logf:
        futs = [ex.submit(build_chunk, c, cfg) for c in chunks]
        for f in as_completed(futs):
            stats, err = f.result()
            for s in stats:
                done[s["sample_id"]] = s
                logf.write(json.dumps(s) + "\n")
            logf.flush()
            if err is not None:
                for g in futs:
                    g.cancel()
                print("\n=== LỖI GHI FILE — DỪNG ===", flush=True)
                print(f"thao tác : {err['op']}")
                print(f"errno    : {err['errno']} ({err['errname']}) — {err['strerror']}")
                print(f"exception: {err['exc']}")
                print(f"file ghi : {err['filename']}")
                print(f"mẫu      : sample_id={err['sample_id']}  nguồn PHP={err['source_php']}", flush=True)
                ex.shutdown(wait=True, cancel_futures=True)
                raise SystemExit(3)
            n += 1
            if n % 25 == 0 or n == len(chunks):
                print(f"  [{label}] {n}/{len(chunks)} chunk", flush=True)
    return [done[r["sample_id"]] for r in rows]
