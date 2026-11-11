"""scripts/emit_paper_numbers.py: sinh macro numbers.tex từ artifact (repo GIẢ trong tmp_path, không đụng paper thật)."""
import importlib.util
import json
import os
import shutil
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _emitter():
    spec = importlib.util.spec_from_file_location("emit_paper_numbers", ROOT / "scripts/emit_paper_numbers.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def _auc(m, sd=0.001):
    return {"auc": {"mean": m, "sd": sd}}


def make_repo(tmp: Path, packaging=(0.5, 0.5, 0.5), summary_test_pos=2):
    """Repo tối thiểu có đủ nguồn; trả về đường dẫn gốc."""
    for d in ("experiments/dataset", "experiments/runs/rq4_ablation", "configs/experiment", "configs/dataset",
              "configs/model", "paper", "data/features_small"):
        (tmp / d).mkdir(parents=True, exist_ok=True)
    w = lambda p, s: (tmp / p).write_text(s)  # noqa: E731
    w("data/features_small/_build_log_obf.jsonl", "")
    w("experiments/dataset/graph_stats.csv", "sample_id\n")
    rows = ["sample_id,path,label,split,source,cluster_id,level,hard,role"]
    spec = {("train", "1"): 3, ("train", "0"): 5, ("val", "1"): 1, ("val", "0"): 2, ("test", "1"): 2,
            ("test", "0"): 4, ("holdout", "1"): 1, ("holdout", "0"): 3}
    k = 0
    for (sp, lab), n in spec.items():
        for i in range(n):
            hard = "1" if (lab == "0" and i == 0) else "0"
            rows.append(f"s{k},p,{lab},{sp},src,c{k},L0,{hard},r"); k += 1
    rows.append(f"s{k},p,1,obf,src,c{k},L2,0,r")                       # dòng obf: không tính vào split chính
    w("experiments/dataset/splits.csv", "\n".join(rows) + "\n")
    w("experiments/dataset/split_summary.json", json.dumps({
        "by_split_label": {"train/1": 3, "train/0": 5, "val/1": 1, "val/0": 2, "test/1": summary_test_pos,
                           "test/0": 4, "holdout/1": 1, "holdout/0": 3},
        "hard_benign_by_split": {"train": 1, "val": 1, "test": 1, "holdout": 1}}))
    w("configs/dataset/obfuscation.yaml", yaml.safe_dump({"levels": [
        {"id": f"L{i}", "kind": "packaging" if i in (2, 3, 5) else "structure"} for i in range(6)]}))
    tt = {"test": _auc(0.99), "holdout": _auc(0.97), **{f"obf_L{i}": _auc(0.9) for i in range(6)}}
    gm = dict(tt, **{f"obf_L{L}": _auc(v) for L, v in zip((2, 3, 5), packaging)})
    w("configs/experiment/probe_on.yaml", yaml.safe_dump({"probe": {
        "graph_stats": ["experiments/dataset/graph_stats.csv"],
        "graph_log_obf": "data/features_small/_build_log_obf.jsonl",
        "out_json": "experiments/dataset/metadata_probe_on.json"}}))
    w("experiments/dataset/char_x.json", json.dumps({"n_pairs": 7, "shallow_auc_subset": {"mean": 0.6, "sd": 0.05},
                                                    "graphmeta_auc_subset": {"mean": 0.7, "sd": 0.02}}))
    per = lambda vals: [{"f1_macro": v} for v in vals]  # noqa: E731
    w("experiments/runs/rq4_ablation/char_matched_test.json", json.dumps({"dataset": "char_x.csv", "n": 9, "variants": {
        "full": {"per_seed": per([0.9, 1.0])}, "rule_e_sem": {"per_seed": per([1.0, 1.0])},
        "no_e_sem": {"per_seed": per([0.8, 1.0])}}}))
    w("configs/experiment/rq4_ablation.yaml", yaml.safe_dump({"falsification": {"c11_margin_pp": 0.5}}))
    w("configs/model/hipag_base.yaml", yaml.safe_dump({
        "model": {"taint_predictor": {"top_k": 8, "warmup_epochs": 3, "tau_floor": 0.3}},
        "esem": {"esem_hop": 12, "max_cand": 4096, "interproc_depth": 2, "cross_function": True}}))
    w("configs/dataset/build_graphs.yaml", yaml.safe_dump({"model_config": "configs/model/hipag_base.yaml",
                                                          "graph": {}}))
    w("paper/numbers.tex", "% header\n\\newcommand{\\Keep}{42}\n\\newcommand{\\HPtopK}{8}  % HP:n\n")
    time.sleep(0.01)
    w("configs/experiment/probe_off.yaml", yaml.safe_dump({"probe": {
        "graph_stats": ["experiments/dataset/graph_stats.csv"],
        "graph_log_obf": "data/features_small/_build_log_obf.jsonl",
        "out_json": "experiments/dataset/metadata_probe_off.json"}}))
    w("experiments/dataset/metadata_probe_on.json", json.dumps({"results": {
        "shallow": {"group_cv": {"auc": {"mean": 0.995, "sd": 0.0002}}, "train_to": tt},
        "graphmeta": {"group_cv": {"auc": {"mean": 0.98, "sd": 0.001}}, "train_to": gm}}}))
    gm_off = dict(tt, **{f"obf_L{L}": _auc(0.5, 0.0) for L in (2, 3, 5)})
    w("experiments/dataset/metadata_probe_off.json", json.dumps({"results": {
        "graphmeta": {"group_cv": {"auc": {"mean": 0.98, "sd": 0.001}}, "train_to": gm_off}}}))
    return tmp


def _by_name(entries):
    return {e["name"]: e for e in entries}


def test_values_formats_and_sources(tmp_path):
    em = _emitter()
    root = make_repo(tmp_path)
    e = _by_name(em.plan(em.collect(root), root / "paper/numbers.tex"))
    assert (e["NTrainPos"]["value"], e["NTrainNeg"]["value"], e["NTestNeg"]["value"]) == ("3", "5", "4")
    assert e["NHardBenignTest"]["value"] == "1"                                  # chỉ benign hard của split test
    assert e["ProbeShallowAucCV"]["value"] == r"\ensuremath{99.50 \pm 0.02}"
    assert e["ProbeGraphmetaAucPacking"]["value"] == r"\ensuremath{50.00 \pm 0.10}"   # mọi mức packaging bằng nhau
    assert e["CharMatchedPairs"]["value"] == "7" and e["CharMatchedN"]["value"] == "9"
    assert e["CharMatchedFullFOne"]["value"] == r"\ensuremath{95.00 \pm 7.07}"   # sd mẫu qua seed
    assert e["CElevenMargin"]["value"] == "0.50" and e["HPnegPerPos"]["value"] == "5"
    assert e["HPtopK"]["status"] == "SAME" and e["NTrainPos"]["status"] == "NEW"


def test_nonuniform_packaging_skips_aggregate_macro(tmp_path):
    em = _emitter()
    root = make_repo(tmp_path, packaging=(0.91, 0.91, 0.85))
    names = {x["name"] for x in em.collect(root)}
    assert "ProbeGraphmetaAucPacking" not in names
    assert {"ProbeGraphmetaAucLTwo", "ProbeGraphmetaAucLThree", "ProbeGraphmetaAucLFive"} <= names
    assert em.SKIPPED and em.SKIPPED[0][0] == "ProbeGraphmetaAucPacking"
    e = _by_name(em.collect(root))                                     # đối chiếu nhánh tắt giải vỏ
    assert e["ProbeGraphmetaNoDeobfAucLTwo"]["mean"] == 0.5 and "ProbeGraphmetaNoDeobfAucTest" in e
    assert e["ProbeGraphmetaNoDeobfAucLTwo"]["src"].startswith("metadata_probe_off.json")


def test_stale_probe_refused(tmp_path):
    em = _emitter()
    root = make_repo(tmp_path)
    future = time.time() + 60                                     # đồ thị bị dựng lại SAU khi chạy probe
    os.utime(root / "data/features_small/_build_log_obf.jsonl", (future, future))
    with pytest.raises(RuntimeError, match="cũ hơn"):
        em.collect(root)


def test_split_summary_mismatch_refused(tmp_path):
    em = _emitter()
    with pytest.raises(ValueError, match="lệch"):
        em.collect(make_repo(tmp_path, summary_test_pos=99))


def test_write_adds_only_and_never_silently_changes(tmp_path):
    em = _emitter()
    root = make_repo(tmp_path)
    tex = root / "paper/numbers.tex"
    tex.write_text(tex.read_text().replace("{\\HPtopK}{8}", "{\\HPtopK}{16}"))      # giá trị cũ lệch nguồn
    ns = lambda **k: type("A", (), {"root": str(root), "numbers_tex": None, "write": True, "force": False, **k})  # noqa: E731
    assert em.main(ns()) == 1                                                    # báo lệch
    txt = tex.read_text()
    assert "\\newcommand{\\Keep}{42}" in txt and "\\newcommand{\\HPtopK}{16}" in txt   # giữ nguyên, không đổi số
    assert "\\newcommand{\\NTrainPos}{3}" in txt and txt.count("\\NTrainPos}") == 1
    em.main(ns())                                                                # chạy lại: không nhân đôi
    assert tex.read_text().count("\\NTrainPos}") == 1
    assert em.main(ns(force=True)) == 0 and "\\newcommand{\\HPtopK}{8}" in tex.read_text()


@pytest.mark.skipif(not (ROOT / "experiments/dataset/splits.csv").exists(), reason="cần artifact thật (data local)")
def test_real_repo_dry_run_covers_paper_needmacros():
    """Trên artifact thật: mọi \\needmacro của main.tex đều đã có trong numbers.tex, hoặc do emitter sinh,
    hoặc bị BỎ kèm lý do (không có macro nào rơi vào [TODO macro] mà không ai biết)."""
    import re
    em = _emitter()
    main = ROOT / "paper/main.tex"
    if not main.exists():
        pytest.skip("không có paper/main.tex")
    have = set(em.existing_values(ROOT / "paper/numbers.tex"))
    names = have | {e["name"] for e in em.collect(ROOT)} | {n for n, _ in em.SKIPPED}
    need = set(re.findall(r"\\needmacro\{([A-Za-z]+)\}", main.read_text()))
    assert need <= names, sorted(need - names)
