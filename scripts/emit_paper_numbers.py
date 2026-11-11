#!/usr/bin/env python3
"""Sinh macro numbers.tex cho các số MÔ TẢ / PROBE / CHAR-MATCHED / CONFIG mà paper/main.tex dùng — đọc từ artifact
đã có trong repo (không train, không chạy probe, KHÔNG gõ tay số).

  python scripts/emit_paper_numbers.py            # chỉ KIỂM: in bảng giá trị + so với paper/numbers.tex
  python scripts/emit_paper_numbers.py --write    # ghi (gộp vào numbers.tex; macro khác giữ nguyên)

An toàn:
  * Không đổi tên / xoá macro nào. Chỉ thêm macro mới hoặc ghi lại macro có giá trị TRÙNG.
  * Macro đã có mà giá trị tính lại KHÁC -> báo DIFF, KHÔNG ghi (trừ --force) — không âm thầm đổi số trong paper.
  * Macro "mồ côi" trước đây ghi bằng lệnh tay (HP*, CharMatchedN) được tính lại từ nguồn để đối chiếu.
Định dạng giống mọi macro khác (eval._fmt_value): đếm -> số nguyên; AUC/F1 -> %, 2 chữ số, ±sd (sd mẫu qua seed);
ngưỡng/hệ số -> 2 chữ số.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hipag.eval import _fmt_value, write_numbers_tex  # noqa: E402
from hipag.utils.metrics import aggregate_seeds  # noqa: E402

SOURCES = {
    "splits": "experiments/dataset/splits.csv",                 # nguồn thật mà thí nghiệm đọc
    "split_summary": "experiments/dataset/split_summary.json",  # chỉ để đối chiếu chéo
    # Probe theo ĐÚNG nhánh đồ thị của các run chính (data/features_small, deobf=on). KHÔNG dùng
    # experiments/dataset/metadata_probe.json: chạy ngày 07/11 trên đồ thị trước UPG-02 (cũ hơn đồ thị hiện tại).
    "probe_cfg": "configs/experiment/probe_on.yaml",
    "probe_off_cfg": "configs/experiment/probe_off.yaml",        # đối chiếu nhánh tắt giải vỏ (UPG-02)
    "main_graph_stats": "experiments/dataset/graph_stats.csv",
    "obf_cfg": "configs/dataset/obfuscation.yaml",
    "char_test": "experiments/runs/rq4_ablation/char_matched_test.json",
    "char_dir": "experiments/dataset",
    "model_cfg": "configs/model/hipag_base.yaml",
    "build_cfg": "configs/dataset/build_graphs.yaml",
    "rq4_cfg": "configs/experiment/rq4_ablation.yaml",
    "numbers": "paper/numbers.tex",
}
SPLIT_NAMES = {"train": "Train", "val": "Val", "test": "Test", "holdout": "Holdout"}
DIGIT = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
NAN = math.nan
SKIPPED: list[tuple[str, str]] = []     # macro paper cần nhưng KHÔNG sinh được (kèm lý do)


def _load(root: Path, key: str):
    p = root / SOURCES[key]
    with open(p) as f:
        return json.load(f) if p.suffix == ".json" else yaml.safe_load(f)


def _check_fresh(result: Path, inputs: list[Path], what: str) -> None:
    """Kết quả phải MỚI hơn mọi đầu vào của nó; cũ hơn -> số tính trên dữ liệu đã bị thay -> dừng."""
    stale = [str(p) for p in inputs if p.exists() and p.stat().st_mtime > result.stat().st_mtime]
    if stale:
        raise RuntimeError(f"{what}: {result} cũ hơn đầu vào {stale} — chạy lại bước tạo ra nó.")


def _msd(d) -> tuple[float, float]:
    return float(d["mean"]), float(d["sd"])


def collect(root: Path = ROOT) -> list[dict]:
    """Danh sách {name, key (định dạng), mean, sd, src, orphan}. key ∈ {n, roc_auc, f1_macro, threshold}."""
    out: list[dict] = []
    SKIPPED.clear()

    def add(name, key, mean, sd=NAN, src="", orphan=False):
        if not name.isalpha():
            raise ValueError(f"tên macro không hợp lệ: {name}")
        out.append({"name": name, "key": key, "mean": float(mean), "sd": float(sd), "src": src, "orphan": orphan})

    # ---- số mẫu theo split: đếm từ splits.csv, đối chiếu chéo split_summary.json (lệch -> dừng)
    import csv
    from collections import Counter
    with open(root / SOURCES["splits"], newline="") as f:
        rows = list(csv.DictReader(f))
    cnt = Counter((r["split"], r["label"]) for r in rows)
    hard = Counter(r["split"] for r in rows if r["label"] == "0" and str(r.get("hard")).lower() in ("1", "true"))
    ss = _load(root, "split_summary")
    for sp in SPLIT_NAMES:
        got = {f"{sp}/{lab}": cnt[(sp, lab)] for lab in ("0", "1")}
        if any(got[k] != ss["by_split_label"][k] for k in got) or hard[sp] != ss["hard_benign_by_split"][sp]:
            raise ValueError(f"splits.csv và split_summary.json lệch ở split={sp}: {got}, hard={hard[sp]} — "
                             "chạy lại 05_make_splits.py.")
    for sp, cap in SPLIT_NAMES.items():
        add(f"N{cap}Pos", "n", cnt[(sp, "1")], src=f"splits.csv split={sp} label=1")
        add(f"N{cap}Neg", "n", cnt[(sp, "0")], src=f"splits.csv split={sp} label=0")
    add("NHardBenignTest", "n", hard["test"], src="splits.csv split=test label=0 hard=1")

    # ---- metadata/shortcut probe (scripts/metadata_probe.py, cấu hình probe_on.yaml; RF, 5 seed)
    from hipag.utils.config import load_config
    pc = load_config(root / SOURCES["probe_cfg"], root=root)["probe"]
    probe_json = root / pc["out_json"]
    _check_fresh(probe_json, [root / g for g in pc["graph_stats"]]
                 + [root / pc["graph_log_obf"], root / SOURCES["splits"]], "probe")
    res = json.loads(probe_json.read_text())["results"]
    psrc = probe_json.name
    sh, gm = res["shallow"], res["graphmeta"]
    add("ProbeShallowAucCV", "roc_auc", *_msd(sh["group_cv"]["auc"]), src=psrc + ":shallow.group_cv")
    add("ProbeShallowAucTest", "roc_auc", *_msd(sh["train_to"]["test"]["auc"]), src=psrc + ":shallow.train->test")
    add("ProbeShallowAucHoldout", "roc_auc", *_msd(sh["train_to"]["holdout"]["auc"]), src=psrc + ":shallow.train->holdout")
    for lv in (1, 2, 4, 5):
        add(f"ProbeShallowAucL{DIGIT[lv]}", "roc_auc", *_msd(sh["train_to"][f"obf_L{lv}"]["auc"]),
            src=psrc + f":shallow.train->obf_L{lv}")
    add("ProbeGraphmetaAucTest", "roc_auc", *_msd(gm["train_to"]["test"]["auc"]), src=psrc + ":graphmeta.train->test")
    # packaging = các mức kind=packaging trong obfuscation.yaml. Luôn sinh macro TỪNG MỨC; macro gộp
    # ProbeGraphmetaAucPacking CHỈ sinh khi mọi mức cho cùng giá trị (không thì một số không đại diện được).
    pack = [lv["id"] for lv in _load(root, "obf_cfg")["levels"] if lv.get("kind") == "packaging"]
    vals = {L: _msd(gm["train_to"][f"obf_{L}"]["auc"]) for L in pack}
    for L, v in vals.items():
        add(f"ProbeGraphmetaAucL{DIGIT[int(L[1:])]}", "roc_auc", *v, src=psrc + f":graphmeta.train->obf_{L}")
    uniform = bool(vals) and max(abs(v[0] - vals[pack[0]][0]) + abs(v[1] - vals[pack[0]][1])
                                 for v in vals.values()) <= 1e-9
    if uniform:
        add("ProbeGraphmetaAucPacking", "roc_auc", *vals[pack[0]],
            src=psrc + f":graphmeta.train->obf_{{{','.join(pack)}}}")
    else:
        SKIPPED.append(("ProbeGraphmetaAucPacking", "graphmeta AUC khác nhau giữa các mức packaging ("
                        + ", ".join(f"{L}={v[0]:.4f}" for L, v in vals.items())
                        + ") — không gộp thành một số; dùng ProbeGraphmetaAucL*"))

    # ---- đối chiếu UPG-02: cùng probe graph-metadata trên nhánh TẮT giải vỏ (probe_off.yaml) — bằng chứng cho việc
    # quy tín hiệu graph-metadata còn sống ở mức packaging cho bước giải vỏ tĩnh. Cùng chốt kiểm độ mới.
    po = load_config(root / SOURCES["probe_off_cfg"], root=root)["probe"]
    off_json = root / po["out_json"]
    _check_fresh(off_json, [root / g for g in po["graph_stats"]]
                 + [root / po["graph_log_obf"], root / SOURCES["splits"]], "probe (deobf=off)")
    gm_off = json.loads(off_json.read_text())["results"]["graphmeta"]
    osrc = off_json.name
    add("ProbeGraphmetaNoDeobfAucTest", "roc_auc", *_msd(gm_off["train_to"]["test"]["auc"]),
        src=osrc + ":graphmeta.train->test")
    for L in pack:
        add(f"ProbeGraphmetaNoDeobfAucL{DIGIT[int(L[1:])]}", "roc_auc", *_msd(gm_off["train_to"][f"obf_{L}"]["auc"]),
            src=osrc + f":graphmeta.train->obf_{L}")

    # ---- character-matched subset: caliper lấy theo đúng file mà lần đánh giá RQ4 đã dùng — bảo đảm macro KHỚP
    # lần đánh giá đó; KHÔNG nói gì về cách chọn caliper (chọn hậu kiểm từ một lần quét, theo shallow AUC <= 0.60)
    ct = _load(root, "char_test")
    cal_path = root / SOURCES["char_dir"] / Path(ct["dataset"]).with_suffix(".json").name
    _check_fresh(cal_path, [root / SOURCES["main_graph_stats"], root / SOURCES["splits"]], "char-matched subset")
    cj = json.loads(cal_path.read_text())
    add("CharMatchedPairs", "n", cj["n_pairs"], src=f"{cal_path.name}.n_pairs")
    add("CharMatchedShallowAuc", "roc_auc", *_msd(cj["shallow_auc_subset"]), src=f"{cal_path.name}.shallow_auc_subset")
    add("CharMatchedGraphmetaAuc", "roc_auc", *_msd(cj["graphmeta_auc_subset"]),
        src=f"{cal_path.name}.graphmeta_auc_subset")
    for var, nm in (("full", "Full"), ("rule_e_sem", "Rule"), ("no_e_sem", "NoESem")):
        per = ct["variants"][var]["per_seed"]
        m, s = aggregate_seeds(per)["f1_macro"]
        add(f"CharMatched{nm}FOne", "f1_macro", m, s, src=f"char_matched_test.{var} ({len(per)} seed)")
    add("CharMatchedN", "n", ct["n"], src="char_matched_test.n", orphan=True)

    # ---- cấu hình
    rq4 = _load(root, "rq4_cfg")
    add("CElevenMargin", "threshold", rq4["falsification"]["c11_margin_pp"], src="rq4_ablation.falsification.c11_margin_pp")
    from hipag.data.build import resolve_graph_cfg
    from hipag.graph.hierarchical_graph import DEFAULT_GRAPH_CFG
    from hipag.train import TRAIN_DEFAULTS
    from hipag.utils.config import deep_merge
    gcfg = deep_merge(DEFAULT_GRAPH_CFG, resolve_graph_cfg(load_config(root / SOURCES["build_cfg"], root=root))["graph"])
    add("HPnegPerPos", "n", gcfg["taint"]["neg_per_pos"], src="graph cfg taint.neg_per_pos (build_graphs + mặc định)")
    mc = _load(root, "model_cfg")
    tp, es = mc["model"]["taint_predictor"], mc["esem"]
    lam = {**TRAIN_DEFAULTS, **(mc.get("train") or {})}["lambda_taint"]
    for name, key, v, src in (
            ("HPtopK", "n", tp["top_k"], "model.taint_predictor.top_k"),
            ("HPwarmup", "n", tp["warmup_epochs"], "model.taint_predictor.warmup_epochs"),
            ("HPtauFloor", "threshold", tp["tau_floor"], "model.taint_predictor.tau_floor"),
            ("HPcandidateHops", "n", es["esem_hop"], "esem.esem_hop"),
            ("HPmaxCand", "n", es["max_cand"], "esem.max_cand"),
            ("HPinterprocDepth", "n", es["interproc_depth"], "esem.interproc_depth"),
            ("HPlambdaTaint", "threshold", lam, "train.lambda_taint (hipag_base + TRAIN_DEFAULTS)")):
        add(name, key, v, src=src, orphan=True)
    return out


def existing_values(path: Path) -> dict[str, str]:
    """{tên macro: phần thân} của numbers.tex (thân có thể chứa ngoặc lồng, vd \\ensuremath{...})."""
    if not path.exists():
        return {}
    out = {}
    for ln in path.read_text().splitlines():
        m = re.match(r"\\(?:newcommand|renewcommand|providecommand)\{\\([A-Za-z]+)\}\{", ln.strip())
        if not m:
            continue
        s, depth, i = ln.strip(), 1, m.end()
        j = i
        while j < len(s) and depth:
            depth += {"{": 1, "}": -1}.get(s[j], 0)
            j += 1
        out[m.group(1)] = s[i:j - 1]
    return out


def plan(entries: list[dict], numbers: Path) -> list[dict]:
    old = existing_values(numbers)
    for e in entries:
        e["value"] = _fmt_value(e["key"], e["mean"], e["sd"])
        e["status"] = "NEW" if e["name"] not in old else ("SAME" if old[e["name"]] == e["value"] else "DIFF")
        e["old"] = old.get(e["name"])
    return entries


def main(args):
    root = Path(args.root).resolve()
    numbers = root / (args.numbers_tex or SOURCES["numbers"])
    entries = plan(collect(root), numbers)
    w = max(len(e["name"]) for e in entries)
    for e in entries:
        tag = e["status"] + (" (mồ côi: đối chiếu)" if e["orphan"] else "")
        extra = f"   cũ={e['old']}" if e["status"] == "DIFF" else ""
        print(f"{e['name']:<{w}}  {e['value']:<32} {tag:<24} <- {e['src']}{extra}")
    for name, why in SKIPPED:
        print(f"{name:<{w}}  {'(KHÔNG SINH)':<32} {'BỎ':<24} <- {why}")
    diffs = [e for e in entries if e["status"] == "DIFF"]
    if not args.write:
        print(f"\n[CHỈ KIỂM] {sum(e['status'] == 'NEW' for e in entries)} mới, "
              f"{sum(e['status'] == 'SAME' for e in entries)} trùng, {len(diffs)} lệch. Thêm --write để ghi.")
        return 1 if diffs else 0
    todo = [e for e in entries if e["status"] == "NEW" or (e["status"] == "DIFF" and args.force)]
    for e in todo:
        write_numbers_tex({e["key"]: (e["mean"], e["sd"])}, str(numbers), prefix="",
                          metric_name_aliases={e["key"]: e["name"]})
    print(f"\nĐã ghi {len(todo)} macro vào {numbers.relative_to(root) if numbers.is_relative_to(root) else numbers}.")
    if diffs and not args.force:
        print(f"KHÔNG ghi {len(diffs)} macro lệch giá trị (cần --force sau khi xác nhận): "
              + ", ".join(e["name"] for e in diffs))
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="ghi vào numbers.tex (mặc định chỉ kiểm)")
    ap.add_argument("--force", action="store_true", help="ghi đè cả macro đã có nhưng lệch giá trị")
    ap.add_argument("--root", default=str(ROOT), help="gốc repo (test dùng thư mục giả)")
    ap.add_argument("--numbers-tex", help="đường dẫn numbers.tex (mặc định paper/numbers.tex)")
    sys.exit(main(ap.parse_args()))
