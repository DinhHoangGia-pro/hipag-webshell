#!/usr/bin/env python3
"""Sinh HỒ SƠ TÁI LẬP repro/manifest.json (máy đọc) + repro/manifest.md (người đọc) từ môi trường HIỆN TẠI và
artifact của các run — mọi số đều đo/đọc, KHÔNG gõ tay.

  python scripts/repro/make_manifest.py

Quy tắc:
  * Dữ liệu chỉ ghi HASH (sha256) + số đếm, không đưa file. Không ghi đường dẫn tuyệt đối / hostname / user.
  * Cờ determinism đọc từ MÃ NGUỒN các hàm set_seed đang dùng (sinh lại khi code đổi -> manifest đổi theo).
  * Mỗi giá trị kèm nguồn (file/lệnh) để kiểm lại được.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata as md
import inspect
import json
import platform
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
OUT = ROOT / "repro"
SEEDS_EXPECTED = [0, 1, 2, 3, 4]
LIBS = ["torch", "torch-geometric", "torch-scatter", "torch-sparse", "pyg-lib", "transformers", "tokenizers",
        "safetensors", "huggingface-hub", "numpy", "scipy", "scikit-learn", "networkx", "pandas", "PyYAML",
        "nvidia-cudnn-cu13", "nvidia-cublas", "nvidia-cuda-runtime"]
CONFIGS = ["configs/model/hipag_base.yaml", "configs/experiment/rq1_baselines.yaml",
           "configs/experiment/rq1_codebert.yaml", "configs/experiment/rq1_detection.yaml",
           "configs/experiment/rq2_obfuscation.yaml", "configs/experiment/rq2_obfuscation_nodeobf.yaml",
           "configs/experiment/rq3_crossdataset.yaml", "configs/experiment/rq4_ablation.yaml",
           "configs/experiment/rq4_ablation_nodeobf.yaml", "configs/experiment/rq5_taint_hparams.yaml",
           "configs/experiment/probe_on.yaml", "configs/experiment/probe_off.yaml",
           "configs/dataset/collect.yaml", "configs/dataset/dedup.yaml", "configs/dataset/split.yaml",
           "configs/dataset/build_graphs.yaml", "configs/dataset/build_graphs_nodeobf.yaml",
           "configs/dataset/obfuscation.yaml", "configs/dataset/obfuscation_nodeobf.yaml", "composer.lock"]


def sha256_file(p: Path) -> str | None:
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def sh(*cmd, cwd=None) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=cwd)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def rel(p) -> str:
    return str(Path(p).resolve().relative_to(ROOT))


def jload(p):
    return json.loads((ROOT / p).read_text())


# ------------------------------------------------------------------ 1–2. nền + GPU
def platform_info() -> dict:
    osr = dict(l.split("=", 1) for l in Path("/etc/os-release").read_text().splitlines() if "=" in l)
    lscpu = dict(l.split(":", 1) for l in (sh("lscpu") or "").splitlines() if ":" in l)
    mem_kb = int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1))
    g = lambda k: lscpu.get(k, "").strip() or None  # noqa: E731
    return {
        "python": platform.python_version(), "python_impl": platform.python_implementation(),
        "os": osr.get("PRETTY_NAME", "").strip('"'), "kernel": platform.release(), "arch": platform.machine(),
        "cpu_model": g("Model name"), "cpu_logical": int(g("CPU(s)") or 0),
        "cpu_cores_per_socket": int(g("Core(s) per socket") or 0), "cpu_sockets": int(g("Socket(s)") or 0),
        "ram_total_gib": round(mem_kb / 1024 ** 2, 1),
        "_source": "platform, /etc/os-release, lscpu, /proc/meminfo",
    }


def gpu_info() -> dict:
    q = sh("nvidia-smi", "--query-gpu=name,memory.total,driver_version,compute_cap", "--format=csv,noheader,nounits")
    head = sh("nvidia-smi") or ""
    m = re.search(r"CUDA Version:\s*([\d.]+)", head)
    out = {"nvidia_smi_available": q is not None}
    if q:
        name, mem, drv, cc = [x.strip() for x in q.splitlines()[0].split(",")]
        out.update({"gpu_model": name, "vram_mib": int(mem), "driver_version": drv, "compute_capability": cc,
                    "driver_max_cuda": m.group(1) if m else None})
    import torch
    cv = torch.backends.cudnn.version()                       # vd 92600 -> "9.26.0"
    out.update({"torch_cuda_build": torch.version.cuda,
                "cudnn_version": f"{cv // 10000}.{cv % 10000 // 100}.{cv % 100}" if cv else None,
                "torch_cuda_available": torch.cuda.is_available()})
    devices = {}
    for led in sorted((ROOT / "experiments/runs").glob("*/ledger.json")):
        d = json.loads(led.read_text())
        devices[rel(led.parent)] = {"device": d.get("device"), "gpu": d.get("gpu"), "synthetic": d.get("synthetic")}
    cb = jload("experiments/runs/rq1_codebert/codebert_rq1_summary.json")
    devices["experiments/runs/rq1_codebert"] = {"device": cb.get("device"), "gpu": cb.get("gpu_name")}
    out["training_device_by_run"] = devices
    out["_source"] = "nvidia-smi; torch.version.cuda; ledger.json / codebert_rq1_summary.json của từng run"
    return out


# ------------------------------------------------------------------ 3. thư viện
def libraries() -> dict:
    py = {}
    for name in LIBS:
        try:
            py[name] = md.version(name)
        except md.PackageNotFoundError:
            py[name] = None                                   # None = KHÔNG cài
    lock = json.loads((ROOT / "composer.lock").read_text())
    php = {p["name"]: {"version": p["version"], "source_ref": (p.get("source") or {}).get("reference")}
           for p in lock["packages"] + lock.get("packages-dev", [])}
    return {"python_packages": py, "composer": php, "php": sh("php", "-r", "echo PHP_VERSION;"),
            "composer_tool": sh("composer", "--version", "--no-ansi"),
            "_source": "importlib.metadata (venv), composer.lock, php -r"}


# ------------------------------------------------------------------ 4. seeds + determinism (đọc từ mã nguồn)
def _flags(src: str) -> dict:
    return {
        "random.seed": "random.seed(" in src, "numpy.random.seed": "np.random.seed(" in src,
        "torch.manual_seed": "torch.manual_seed(" in src, "torch.cuda.manual_seed_all": "manual_seed_all(" in src,
        "cudnn.deterministic=True": "cudnn.deterministic = True" in src,
        "cudnn.benchmark=False": "cudnn.benchmark = False" in src,
        "PYTHONHASHSEED_set_at_runtime": "PYTHONHASHSEED" in src,
    }


def determinism() -> dict:
    from hipag.utils.seed import set_seed as hipag_seed
    from scripts.run_baselines import set_seed as base_seed
    code = "".join(p.read_text(errors="replace") for p in list((ROOT / "src").rglob("*.py"))
                   + list((ROOT / "scripts").rglob("*.py")) if p.name != "make_manifest.py")
    cb_src = (ROOT / "scripts/run_codebert_baseline.py").read_text()
    return {
        "seeds": SEEDS_EXPECTED,
        "hipag_set_seed": {"where": "src/hipag/utils/seed.py:set_seed", **_flags(inspect.getsource(hipag_seed))},
        "codebert_and_harness_baselines_set_seed": {"where": "scripts/run_baselines.py:set_seed",
                                                    **_flags(inspect.getsource(base_seed))},
        "torch.use_deterministic_algorithms": "use_deterministic_algorithms" in code,
        "CUBLAS_WORKSPACE_CONFIG": "CUBLAS_WORKSPACE_CONFIG" in code,
        "codebert_amp_fp16_on_cuda": "torch.float16" in cb_src and "autocast" in cb_src,
        "torch_scatter_installed": _installed("torch-scatter"),
        "notes": [
            "PYTHONHASHSEED được gán TRONG tiến trình -> chỉ tác dụng với tiến trình con, không cố định hash của chính nó.",
            "Không bật torch.use_deterministic_algorithms; scatter của PyG trên CUDA (không có torch-scatter) có thể "
            "không tất định tuyệt đối -> kết quả báo mean±sd qua 5 seed.",
        ],
        "_source": "inspect.getsource(set_seed) + grep src/ scripts/",
    }


def _installed(name):
    try:
        md.version(name)
        return True
    except md.PackageNotFoundError:
        return False


# ------------------------------------------------------------------ 5. CodeBERT
def codebert() -> dict:
    run = ROOT / "experiments/runs/rq1_codebert"
    s = jload("experiments/runs/rq1_codebert/codebert_rq1_summary.json")
    ref = run / "hf_cache/models--microsoft--codebert-base/refs/main"
    cfg_path = ROOT / "configs/experiment/rq1_codebert.yaml"
    per_seed = []
    for sd in SEEDS_EXPECTED:
        m = json.loads((run / f"seed_{sd}/metrics.json").read_text())
        per_seed.append({"seed": m["seed"], "run_fingerprint": m["run_fingerprint"], "best_epoch": m["best_epoch"],
                         "epochs_run": len(m.get("history") or []), "val_pr_auc": m.get("val_pr_auc"),
                         "elapsed_hours": round(m["elapsed_seconds"] / 3600, 2)})
    t = s["train"]
    wc = t.get("window_counts", {})
    return {
        "model_id": s["model"], "model_revision_recorded": s.get("model_revision"),
        "hf_cache_refs_main": ref.read_text().strip() if ref.exists() else None,
        "revision_pinned_in_from_pretrained": False,
        "length_strategy": s.get("length_strategy"), "windowing_details": s.get("windowing_details"),
        "files_hitting_window_cap": {sp: f"{v['files_with_8_windows']}/{v['files']}" for sp, v in wc.items()},
        "optimizer": t["optim"], "lr": t["lr"], "weight_decay": t["weight_decay"], "max_epochs": t["max_epochs"],
        "patience": t["patience"], "selection": t["select"], "loss": t["loss"],
        "batch_size_files": t["batch_size_files"], "window_batch_size": t["window_batch_size"],
        "gradient_checkpointing": t["gradient_checkpointing"], "max_grad_norm": s.get("train_config", {}).get("max_grad_norm"),
        "input_artifact": s["input_artifact"], "input_sha256_recorded": s["input_sha256"],
        "input_sha256_now": sha256_file(ROOT / s["input_artifact"]),
        "config": rel(cfg_path), "config_sha256_recorded": s["config_sha256"],
        "config_sha256_now": sha256_file(cfg_path),
        "fingerprints_identical_across_seeds": len({p["run_fingerprint"] for p in per_seed}) == 1,
        "per_seed": per_seed, "script": "scripts/run_codebert_baseline.py",
        "_source": "experiments/runs/rq1_codebert/{codebert_rq1_summary.json, seed_*/metrics.json, hf_cache/.../refs/main}",
    }


# ------------------------------------------------------------------ 6. HiPaG
def hipag() -> dict:
    from hipag.train import TRAIN_DEFAULTS
    led = jload("experiments/runs/rq4_ablation/ledger.json")
    c, m = led["config"], led["config"]["model"]
    tr = {**TRAIN_DEFAULTS, **(c.get("train") or {})}
    sw = jload("experiments/runs/rq5_taint_hparams/sweep_best.json")
    rq5 = jload("experiments/runs/rq5_taint_hparams/ledger.json")
    return {
        "optimizer": tr["optimizer"], "lr": tr["lr"], "weight_decay": tr["weight_decay"], "max_epochs": tr["epochs"],
        "batch_size": tr["batch_size"], "early_stop_patience": tr["patience"],
        "selection_metric": f"val {tr['select_metric']}", "grad_clip": tr["grad_clip"],
        "lambda_taint": tr["lambda_taint"], "decision_threshold": tr["threshold"],
        "taint_predictor": m["taint_predictor"], "esem": c.get("esem"),
        "architecture": {k: m.get(k) for k in ("token_transformer", "intra_gatv2", "inter_transformer", "dropout", "pool")},
        "taint_hparam_sweep": {"grid": rq5["config"].get("sweep"), "fixed": {"tau_floor": m["taint_predictor"]["tau_floor"]},
                               "select": sw["select"], "best": sw["best"], "best_overrides": sw["overrides"],
                               "best_val_mean_sd": sw["mean_sd"], "n_seeds": sw["n_seeds"]},
        "main_run": {"dir": "experiments/runs/rq4_ablation", "seeds": led["seeds"], "variants": led["variants"],
                     "time_utc": led["time_utc"], "device": led["device"]},
        "_source": "experiments/runs/rq4_ablation/ledger.json (config đã dùng) + src/hipag/train.py:TRAIN_DEFAULTS "
                   "+ experiments/runs/rq5_taint_hparams/{sweep_best.json, ledger.json}",
    }


# ------------------------------------------------------------------ 7. dữ liệu (chỉ hash + đếm)
def _git_head(p: Path):
    return sh("git", "-C", str(p), "rev-parse", "HEAD") if (p / ".git").exists() else None


def data() -> dict:
    ds = "experiments/dataset"
    rows = list(csv.DictReader(open(ROOT / ds / "splits.csv", newline="")))
    per = {}
    for sp in ["train", "val", "test", "holdout", "obf"]:
        r = [x for x in rows if x["split"] == sp]
        lab = Counter(x["label"] for x in r)
        per[sp] = {"n": len(r), "n_webshell": lab["1"], "n_benign": lab["0"],
                   "sample_ids_sha256": sha256_text("\n".join(sorted(x["sample_id"] for x in r)))}
    man = list(csv.DictReader(open(ROOT / ds / "manifest.csv", newline="")))
    by_src = Counter((x["source"], x["label"]) for x in man)
    col = yaml.safe_load((ROOT / "configs/dataset/collect.yaml").read_text())
    tsv = {l.split("\t")[0]: l.rstrip("\n").split("\t") for l in open(ROOT / ds / "benign2_sources.tsv") if l.strip()}
    paths = {s["name"]: s for k in ("webshell_sources", "benign_sources", "hard_benign") for s in col.get(k, [])}
    zips = {"cycle183": ["data/dl/cycle183.zip"],
            "c01dsnap": ["data/dl/c01dsnap_Webshell_Black.zip", "data/dl/c01dsnap_Webshell_webshell.zip"],
            "c01dsnap_benign": ["data/dl/c01dsnap_Webshell_White.zip"]}
    sources = {}
    for name in sorted({x["source"] for x in man}):
        e = {"n_webshell": by_src[(name, "1")], "n_benign": by_src[(name, "0")]}
        if name in tsv:
            e.update({"repo": f"https://github.com/{tsv[name][1]}", "pinned_commit": tsv[name][2],
                      "pin": "benign2_sources.tsv"})
        elif name in paths:
            e["url"] = paths[name].get("url")
            head = _git_head(ROOT / paths[name]["path"])
            if head:
                e.update({"pinned_commit": head, "pin": "git HEAD của bản clone đã dùng"})
        if name in zips:
            e["archives_sha256"] = {Path(z).name: sha256_file(ROOT / z) for z in zips[name]}
            e["pin"] = "sha256 của file nén đã tải (không có commit/revision cho nội dung)"
            if name == "cycle183":
                e["repo_commit"] = _git_head(ROOT / "data/_repos/cycle183_repo")
        sources[name] = e
    files = ["splits.csv", "manifest.csv", "split_summary.json", "obfuscation_manifest.csv",
             "obfuscation_manifest_nodeobf.csv", "benign2_sources.tsv", "clusters.csv"]
    return {
        "split_counts": per,
        "file_sha256": {f"{ds}/{f}": sha256_file(ROOT / ds / f) for f in files},
        "canonical_inputs_jsonl": {"path": "experiments/runs/rq1_codebert/canonical_inputs.jsonl",
                                   "sha256": sha256_file(ROOT / "experiments/runs/rq1_codebert/canonical_inputs.jsonl")},
        "manifest_rows": len(man), "split_rows_main": sum(per[s]["n"] for s in ("train", "val", "test", "holdout")),
        "sources": sources,
        "on_disk_but_not_in_manifest": ["data/_repos/mwf_repo (MWF; thay bằng c01dsnap làm holdout)",
                                        "data/dl/nbuser32_PHP-Webshell-Dataset_php_webshell_dataset.jsonl"],
        "_source": "experiments/dataset/*.csv|json|tsv, configs/dataset/collect.yaml, git HEAD các clone trong data/raw",
    }


# ------------------------------------------------------------------ mã + config
def code_state() -> dict:
    files = sorted([*ROOT.glob("src/**/*.py"), *ROOT.glob("scripts/**/*.py"), *ROOT.glob("tools/php/*.php"),
                    *ROOT.glob("configs/**/*.yaml"), ROOT / "composer.lock", ROOT / "requirements.txt"])
    tree = sha256_text("".join(f"{rel(p)}\t{sha256_file(p)}\n" for p in files if p.is_file()))
    dirty = (sh("git", "status", "--porcelain", cwd=ROOT) or "").splitlines()
    commits = {rel(l.parent): json.loads(l.read_text()).get("git_commit")
               for l in sorted((ROOT / "experiments/runs").glob("*/ledger.json"))}
    return {"git_head": sh("git", "rev-parse", "HEAD", cwd=ROOT), "git_dirty_entries": len(dirty),
            "git_dirty_sample": dirty[:15], "code_tree_sha256": tree, "code_tree_files": len(files),
            "commit_recorded_in_run_ledgers": commits,
            "note": "Các ledger ghi git_commit lúc chạy nhưng working tree khi đó có thay đổi CHƯA commit -> commit "
                    "không ghim được mã đã chạy. code_tree_sha256 là trạng thái mã HIỆN TẠI (lúc sinh manifest).",
            "configs_sha256": {c: sha256_file(ROOT / c) for c in CONFIGS}}


# ------------------------------------------------------------------ xuất
def paper_numbers(m: dict) -> dict:
    g, lib = m["gpu"], m["libraries"]["python_packages"]
    return {"Python": m["platform"]["python"], "PyTorch": lib["torch"], "PyTorch Geometric": lib["torch-geometric"],
            "Transformers": lib["transformers"], "GPU": f"{g.get('gpu_model')} ({g.get('vram_mib')} MiB)",
            "CUDA (torch build)": g["torch_cuda_build"], "CUDA (driver max)": g.get("driver_max_cuda"),
            "NVIDIA driver": g.get("driver_version"), "cuDNN": g["cudnn_version"],
            "PHP-Parser": m["libraries"]["composer"].get("nikic/php-parser", {}).get("version"),
            "PHP": m["libraries"]["php"], "CodeBERT revision": m["codebert"]["model_revision_recorded"],
            "OS": m["platform"]["os"], "CPU": m["platform"]["cpu_model"], "RAM (GiB)": m["platform"]["ram_total_gib"]}


def to_md(m: dict) -> str:
    p, g, lib, det, cb, hp, dt, cs = (m[k] for k in ("platform", "gpu", "libraries", "determinism", "codebert",
                                                       "hipag", "data", "code"))
    L = [f"# Hồ sơ tái lập HiPaG", "",
         f"Sinh tự động bởi `scripts/repro/make_manifest.py` lúc {m['generated_utc']} (UTC). "
         "Bản máy đọc: `repro/manifest.json`. Dữ liệu chỉ ghi hash + số đếm, không kèm file.", "",
         "## Số trích cho paper", "", "| Mục | Giá trị |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in m["paper_numbers"].items()]
    L += ["", "## 1. Nền", "", f"- Python {p['python']} ({p['python_impl']}); {p['os']}, kernel {p['kernel']} ({p['arch']})",
          f"- CPU: {p['cpu_model']} — {p['cpu_sockets']} socket × {p['cpu_cores_per_socket']} nhân, {p['cpu_logical']} luồng",
          f"- RAM: {p['ram_total_gib']} GiB", "",
          "## 2. GPU", "", f"- {g.get('gpu_model')}, {g.get('vram_mib')} MiB VRAM, compute capability {g.get('compute_capability')}",
          f"- Driver {g.get('driver_version')} (hỗ trợ tối đa CUDA {g.get('driver_max_cuda')}); PyTorch build CUDA "
          f"{g['torch_cuda_build']}, cuDNN {g['cudnn_version']}",
          "- Thiết bị train theo run (từ ledger/summary): " + "; ".join(
              f"`{k}` = {v.get('device')}" + (" (synthetic)" if v.get("synthetic") else "")
              for k, v in g["training_device_by_run"].items()), "",
          "## 3. Thư viện", "", "| Gói | Phiên bản |", "|---|---|"]
    L += [f"| {k} | {v if v else 'không cài'} |" for k, v in lib["python_packages"].items()]
    L += [f"| {k} (composer) | {v['version']} (`{(v['source_ref'] or '')[:12]}`) |" for k, v in lib["composer"].items()]
    L += [f"| PHP | {lib['php']} |", "", "## 4. Seed và determinism", "", f"- Seed: {det['seeds']}"]
    for key, title in (("hipag_set_seed", "HiPaG"), ("codebert_and_harness_baselines_set_seed", "CodeBERT + baseline harness")):
        f = det[key]
        on = [k for k, v in f.items() if k != "where" and v]
        off = [k for k, v in f.items() if k != "where" and not v]
        L.append(f"- {title} (`{f['where']}`): đặt {', '.join(on)}; KHÔNG đặt tường minh: {', '.join(off) or '—'}")
    L.append("- Mặc định PyTorch khi không đặt: cudnn.deterministic=False, cudnn.benchmark=False.")
    L += [f"- `torch.use_deterministic_algorithms`: {'có' if det['torch.use_deterministic_algorithms'] else 'không'}; "
          f"`CUBLAS_WORKSPACE_CONFIG`: {'có' if det['CUBLAS_WORKSPACE_CONFIG'] else 'không'}; "
          f"torch-scatter: {'có' if det['torch_scatter_installed'] else 'không cài'}; "
          f"CodeBERT AMP fp16 trên CUDA: {'có' if det['codebert_amp_fp16_on_cuda'] else 'không'}"]
    L += [f"- {n}" for n in det["notes"]]
    L += ["", "## 5. CodeBERT", "", f"- Model `{cb['model_id']}`, revision `{cb['model_revision_recorded']}` "
          f"(HF cache refs/main `{cb['hf_cache_refs_main']}`; `from_pretrained` không ghim revision — revision thực "
          "tế được ghi vào danh tính run)",
          f"- Độ dài: {cb['length_strategy']} — {cb['windowing_details']}",
          f"- File chạm giới hạn 8 cửa sổ: " + ", ".join(f"{k} {v}" for k, v in cb["files_hitting_window_cap"].items()),
          f"- {cb['optimizer']} lr {cb['lr']}, weight decay {cb['weight_decay']}, tối đa {cb['max_epochs']} epoch, "
          f"patience {cb['patience']}, chọn theo {cb['selection']}; batch {cb['batch_size_files']} file / "
          f"{cb['window_batch_size']} cửa sổ, grad-norm {cb['max_grad_norm']}, gradient checkpointing {cb['gradient_checkpointing']}",
          f"- Loss: {cb['loss']}",
          f"- Đầu vào `{cb['input_artifact']}` sha256 `{cb['input_sha256_now']}` "
          f"({'khớp' if cb['input_sha256_now'] == cb['input_sha256_recorded'] else 'LỆCH'} lúc chạy); config "
          f"`{cb['config']}` ({'khớp' if cb['config_sha256_now'] == cb['config_sha256_recorded'] else 'LỆCH'} lúc chạy)", "",
          "| Seed | run_fingerprint | best epoch | epoch chạy | val PR-AUC | giờ |", "|---|---|---|---|---|---|"]
    L += [f"| {s['seed']} | `{s['run_fingerprint']}` | {s['best_epoch']} | {s['epochs_run']} | {s['val_pr_auc']:.4f} | "
          f"{s['elapsed_hours']} |" for s in cb["per_seed"]]
    tp, sw = hp["taint_predictor"], hp["taint_hparam_sweep"]
    L += ["", f"Cả 5 seed cùng fingerprint: {cb['fingerprints_identical_across_seeds']}.", "",
          "## 6. HiPaG", "", f"- {hp['optimizer']} lr {hp['lr']}, weight decay {hp['weight_decay']}, tối đa "
          f"{hp['max_epochs']} epoch, batch {hp['batch_size']}, early stop patience {hp['early_stop_patience']} theo "
          f"{hp['selection_metric']}; grad clip {hp['grad_clip']}; λ_taint {hp['lambda_taint']}; ngưỡng {hp['decision_threshold']}",
          f"- Taint predictor: k (top_k) = {tp['top_k']}, W (warmup_epochs) = {tp['warmup_epochs']}, "
          f"τ_min (tau_floor) = {tp['tau_floor']}, pos_weight {tp['pos_weight']}, MLP {tp['mlp_hidden']}",
          f"- Sweep (RQ5, {sw['n_seeds']} seed): lưới {sw['grid']}, cố định {sw['fixed']}, chọn theo "
          f"{sw['select']['split']} {sw['select']['metric']} -> `{sw['best']}` ({sw['best_val_mean_sd'][0]:.4f} ± "
          f"{sw['best_val_mean_sd'][1]:.4f})",
          f"- E_sem: {hp['esem']}", f"- Kiến trúc: {hp['architecture']}",
          f"- Run chính `{hp['main_run']['dir']}`: seed {hp['main_run']['seeds']}, thiết bị {hp['main_run']['device']}, "
          f"{len(hp['main_run']['variants'])} biến thể", "",
          "## 7. Dữ liệu (chỉ hash + số đếm)", "", "| Split | n | webshell | benign | sha256(sample_id đã sắp) |",
          "|---|---|---|---|---|"]
    L += [f"| {k} | {v['n']} | {v['n_webshell']} | {v['n_benign']} | `{v['sample_ids_sha256']}` |"
          for k, v in dt["split_counts"].items()]
    L += ["", "| File | sha256 |", "|---|---|"]
    L += [f"| `{k}` | `{v}` |" for k, v in dt["file_sha256"].items()]
    L += [f"| `{dt['canonical_inputs_jsonl']['path']}` | `{dt['canonical_inputs_jsonl']['sha256']}` |", "",
          "| Nguồn | webshell | benign | ghim phiên bản |", "|---|---|---|---|"]
    for n, e in dt["sources"].items():
        pin = e.get("pinned_commit") and f"commit `{e['pinned_commit'][:12]}` ({e.get('repo') or e.get('url')})"
        if "archives_sha256" in e:
            pin = "; ".join(f"`{z}` sha256 `{h[:16]}…`" for z, h in e["archives_sha256"].items())
            if e.get("repo_commit"):
                pin += f"; repo commit `{e['repo_commit'][:12]}`"
        L.append(f"| {n} | {e['n_webshell']} | {e['n_benign']} | {pin or 'KHÔNG ghim'} |")
    L += ["", "Có trên đĩa nhưng không dùng: " + "; ".join(dt["on_disk_but_not_in_manifest"]), "",
          "## 8. Mã và config", "", f"- git HEAD `{cs['git_head']}`; {cs['git_dirty_entries']} mục chưa commit; "
          f"code_tree_sha256 `{cs['code_tree_sha256']}` ({cs['code_tree_files']} file)",
          f"- {cs['note']}", "- Commit ghi trong ledger: " + ", ".join(f"`{k}` {(v or '')[:10]}" for k, v in
                                                                    cs["commit_recorded_in_run_ledgers"].items()),
          "", "| Config | sha256 |", "|---|---|"]
    L += [f"| `{k}` | `{v}` |" for k, v in cs["configs_sha256"].items()]
    return "\n".join(L) + "\n"


def main():
    m = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "platform": platform_info(), "gpu": gpu_info(), "libraries": libraries(), "determinism": determinism(),
         "codebert": codebert(), "hipag": hipag(), "data": data(), "code": code_state()}
    m["paper_numbers"] = paper_numbers(m)
    OUT.mkdir(exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")
    (OUT / "manifest.md").write_text(to_md(m))
    print(json.dumps(m["paper_numbers"], indent=1, ensure_ascii=False))
    print(f"-> {rel(OUT / 'manifest.json')}, {rel(OUT / 'manifest.md')}")


if __name__ == "__main__":
    main()
