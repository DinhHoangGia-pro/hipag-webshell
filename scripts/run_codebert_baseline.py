#!/usr/bin/env python3
"""Train resumable CodeBERT RQ1 baseline on the shared canonical PHP split."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from hipag.data.dataset import WebshellGraphDataset  # noqa: E402
from hipag.eval import evaluate  # noqa: E402
from hipag.utils.config import load_config  # noqa: E402
from hipag.utils.metrics import aggregate_seeds  # noqa: E402
from scripts.run_baselines import canonical_source_bytes, read_csv, set_seed  # noqa: E402

METRICS = (
    "f1_macro",
    "mcc",
    "pr_auc",
    "fpr_at_tpr95",
    "prec_at_base_10pct",
    "prec_at_base_1pct",
    "prec_at_base_0p1pct",
)
SPLITS = ("train", "val", "test", "holdout")
MODEL_NAME = "microsoft/codebert-base"
LENGTH_STRATEGY = "sliding-window 512 stride 384 mean-pool cap8"


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False, default=float) + "\n")
    temporary.replace(path)


def atomic_torch_save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(value, temporary)
    temporary.replace(path)


def load_split_rows(cfg: dict) -> tuple[dict[str, list[dict]], dict[str, int]]:
    split_csv = ROOT / cfg["splits"]
    feature_dir = ROOT / cfg["features_dir"]
    by_split: dict[str, list[dict]] = {}
    sizes: dict[str, int] = {}
    for split in SPLITS:
        dataset = WebshellGraphDataset(str(split_csv), str(feature_dir), split=split)
        if not len(dataset):
            raise RuntimeError(f"Harness split {split!r} is empty")
        if dataset.skipped:
            raise RuntimeError(
                f"Harness skipped {len(dataset.skipped)} {split} graphs; "
                "refusing to silently evaluate a different sample set"
            )
        by_split[split] = dataset.rows
        sizes[split] = len(dataset)
    return by_split, sizes


def canonical_input_artifact(cfg: dict, rows_by_split: dict[str, list[dict]], out_dir: Path) -> tuple[Path, str]:
    path = out_dir / "canonical_inputs.jsonl"
    split_path = ROOT / cfg["splits"]
    manifest_path = ROOT / cfg["manifest"]
    signature = hashlib.sha256(
        (
            sha256_file(split_path)
            + sha256_file(manifest_path)
            + json.dumps({split: [r["sample_id"] for r in rows_by_split[split]]
                          for split in SPLITS}, sort_keys=True)
        ).encode()
    ).hexdigest()

    if path.exists():
        with path.open(encoding="utf-8") as f:
            first = json.loads(f.readline())
        if first.get("_metadata", {}).get("signature") != signature:
            raise RuntimeError(
                f"Existing canonical input artifact {path} does not match the current split/manifest"
            )
    else:
        all_rows = [row for split in SPLITS for row in rows_by_split[split]]
        source_bytes = canonical_source_bytes(cfg, all_rows)
        if len(source_bytes) != len(all_rows):
            raise RuntimeError("Canonicalizer returned a different number of rows than the harness split")
        metadata = {
            "_metadata": {
                "schema_version": 1,
                "signature": signature,
                "canonicalizer": "scripts.run_baselines.canonical_source_bytes",
                "canonicalizer_implementation": "tools/php/canonicalize.php",
                "split_csv": str(split_path.relative_to(ROOT)),
                "manifest": str(manifest_path.relative_to(ROOT)),
                "split_sizes": {split: len(rows_by_split[split]) for split in SPLITS},
            }
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".jsonl.tmp")
        with temporary.open("w", encoding="utf-8") as f:
            f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
            for row, raw in zip(all_rows, source_bytes):
                record = {
                    "sample_id": row["sample_id"],
                    "split": row["split"],
                    "label": int(float(row["label"])),
                    "canonical_text": raw.decode("utf-8", "replace"),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        temporary.replace(path)

    return path, sha256_file(path)


def load_canonical_documents(path: Path) -> dict[str, list[dict]]:
    documents = {split: [] for split in SPLITS}
    with path.open(encoding="utf-8") as f:
        metadata = json.loads(f.readline())
        if "_metadata" not in metadata:
            raise RuntimeError(f"Canonical input file lacks metadata header: {path}")
        for line in f:
            row = json.loads(line)
            split = row["split"]
            if split not in documents:
                raise RuntimeError(f"Unexpected split in canonical input artifact: {split}")
            documents[split].append(row)
    return documents


def tokenize_documents(tokenizer, documents: dict[str, list[dict]], cfg: dict) -> dict[str, list[dict]]:
    max_length = int(cfg["max_length"])
    stride = int(cfg["stride"])
    cap = int(cfg["max_windows_per_file"])
    special_tokens = tokenizer.num_special_tokens_to_add(pair=False)
    content_window = max_length - special_tokens
    max_content_tokens = content_window + (cap - 1) * stride
    if content_window <= 0 or stride <= 0 or stride >= max_length:
        raise ValueError("Invalid CodeBERT max_length/stride configuration")

    tokenized: dict[str, list[dict]] = {}
    total = sum(len(rows) for rows in documents.values())
    done = 0
    for split in SPLITS:
        tokenized[split] = []
        for row in documents[split]:
            encoded = tokenizer(
                row["canonical_text"],
                add_special_tokens=False,
                truncation=True,
                max_length=max_content_tokens,
            )
            content_ids = encoded["input_ids"]
            windows: list[list[int]] = []
            if not content_ids:
                windows = [tokenizer.build_inputs_with_special_tokens([])]
            else:
                start = 0
                while start < len(content_ids) and len(windows) < cap:
                    chunk = content_ids[start:start + content_window]
                    windows.append(tokenizer.build_inputs_with_special_tokens(chunk))
                    if start + content_window >= len(content_ids):
                        break
                    start += stride
            tokenized[split].append({
                "sample_id": row["sample_id"],
                "label": int(row["label"]),
                "windows": windows,
            })
            done += 1
            if done % 1000 == 0 or done == total:
                print(f"  tokenized {done}/{total} canonical files", flush=True)
    return tokenized


class CodeBertClassifier(nn.Module):
    def __init__(self, encoder: nn.Module, hidden_size: int):
        super().__init__()
        self.encoder = encoder
        self.dropout = nn.Dropout(0.1)
        self.classifier = nn.Linear(hidden_size, 1)

    def forward(self, window_batches: list[dict[str, torch.Tensor]], owners: list[int], n_files: int):
        outputs = []
        for batch in window_batches:
            encoded = self.encoder(**batch, return_dict=True)
            pooled = encoded.pooler_output
            if pooled is None:
                raise RuntimeError("CodeBERT encoder returned no pooled_output")
            outputs.append(pooled)
        window_states = torch.cat(outputs, dim=0)
        owner_index = torch.tensor(owners, device=window_states.device, dtype=torch.long)
        pooled_sum = window_states.new_zeros((n_files, window_states.shape[-1]))
        pooled_sum.index_add_(0, owner_index, window_states)
        counts = torch.bincount(owner_index, minlength=n_files).to(window_states.dtype).unsqueeze(1)
        file_states = pooled_sum / counts.clamp_min(1)
        return self.classifier(self.dropout(file_states)).squeeze(-1)


def make_window_batches(tokenizer, files: list[dict], window_batch_size: int, device: torch.device):
    all_windows: list[list[int]] = []
    owners: list[int] = []
    labels: list[int] = []
    for owner, row in enumerate(files):
        if not row["windows"]:
            raise RuntimeError(f"No CodeBERT windows for sample {row['sample_id']}")
        all_windows.extend(row["windows"])
        owners.extend([owner] * len(row["windows"]))
        labels.append(int(row["label"]))

    batches = []
    for start in range(0, len(all_windows), window_batch_size):
        batch_ids = all_windows[start:start + window_batch_size]
        encoded = tokenizer.pad(
            {"input_ids": batch_ids},
            padding=True,
            return_tensors="pt",
        )
        batches.append({key: value.to(device) for key, value in encoded.items()})
    return batches, owners, torch.tensor(labels, dtype=torch.float32, device=device)


def score_dataset(model, tokenizer, rows: list[dict], cfg: dict, device: torch.device,
                  batch_size_files: int, window_batch_size: int, use_amp: bool):
    model.eval()
    labels: list[int] = []
    scores: list[float] = []
    for start in range(0, len(rows), batch_size_files):
        files = rows[start:start + batch_size_files]
        window_batches, owners, y = make_window_batches(tokenizer, files, window_batch_size, device)
        with torch.inference_mode(), torch.autocast(
            device_type=device.type, dtype=torch.float16, enabled=use_amp
        ):
            logits = model(window_batches, owners, len(files))
            probability = torch.sigmoid(logits)
        labels.extend(y.cpu().numpy().astype(int).tolist())
        scores.extend(probability.float().cpu().numpy().tolist())
    return np.asarray(labels, dtype=np.int64), np.asarray(scores, dtype=np.float64)


def rng_state() -> dict:
    state = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch_cpu": torch.get_rng_state(),
    }
    if torch.cuda.is_available():
        state["torch_cuda"] = torch.cuda.get_rng_state_all()
    return state


def restore_rng_state(state: dict) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch_cpu"].detach().cpu())
    if torch.cuda.is_available() and "torch_cuda" in state:
        torch.cuda.set_rng_state_all([item.detach().cpu() for item in state["torch_cuda"]])


def fit_seed(seed: int, tokenized: dict[str, list[dict]], tokenizer, encoder, cfg: dict,
             device: torch.device, seed_dir: Path, fingerprint: str) -> dict:
    seed_started = time.monotonic()
    metrics_path = seed_dir / "metrics.json"
    best_path = seed_dir / "best.pt"
    last_path = seed_dir / "last.pt"
    if metrics_path.exists():
        result = json.loads(metrics_path.read_text())
        if result.get("run_fingerprint") != fingerprint:
            raise RuntimeError(f"Seed {seed} result exists but is from a different run")
        print(f"  seed {seed}: already complete; reusing saved metrics", flush=True)
        return result

    train_cfg = cfg["codebert"]
    batch_size_files = int(train_cfg["batch_size_files"])
    window_batch_size = int(train_cfg["window_batch_size"])
    use_amp = device.type == "cuda"
    model = CodeBertClassifier(encoder, int(encoder.config.hidden_size)).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(train_cfg["lr"]),
        weight_decay=float(train_cfg["weight_decay"]),
    )
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    start_epoch, best_pr_auc, best_epoch, bad_epochs, history = 0, -math.inf, -1, 0, []
    if last_path.exists():
        checkpoint = torch.load(last_path, map_location=device, weights_only=False)
        if checkpoint.get("run_fingerprint") != fingerprint:
            raise RuntimeError(f"Seed {seed} checkpoint exists but is from a different run")
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        scaler.load_state_dict(checkpoint["scaler"])
        start_epoch = int(checkpoint["epoch"]) + 1
        best_pr_auc = float(checkpoint["best_pr_auc"])
        best_epoch = int(checkpoint["best_epoch"])
        bad_epochs = int(checkpoint["bad_epochs"])
        history = checkpoint["history"]
        restore_rng_state(checkpoint["rng"])
        print(f"  seed {seed}: resuming at epoch {start_epoch + 1}", flush=True)

    if not best_path.exists() and start_epoch > 0:
        raise RuntimeError(f"Seed {seed} has a resume checkpoint but no best checkpoint")
    if train_cfg.get("gradient_checkpointing", True):
        model.encoder.gradient_checkpointing_enable()

    epochs_remaining = start_epoch < int(train_cfg["epochs"]) and bad_epochs < int(train_cfg["patience"])
    for epoch in range(start_epoch, int(train_cfg["epochs"]) if epochs_remaining else start_epoch):
        epoch_started = time.monotonic()
        model.train()
        order_gen = torch.Generator(device="cpu").manual_seed(seed * 1_000_003 + epoch)
        order = torch.randperm(len(tokenized["train"]), generator=order_gen).tolist()
        for batch_no, offset in enumerate(range(0, len(order), batch_size_files), start=1):
            files = [tokenized["train"][i] for i in order[offset:offset + batch_size_files]]
            window_batches, owners, labels = make_window_batches(tokenizer, files, window_batch_size, device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
                logits = model(window_batches, owners, len(files))
                loss = nn.functional.binary_cross_entropy_with_logits(logits, labels)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), float(train_cfg["max_grad_norm"]))
            scaler.step(optimizer)
            scaler.update()
            if batch_no % 100 == 0:
                print(
                    f"    seed={seed} epoch={epoch + 1} batch={batch_no}/{math.ceil(len(order) / batch_size_files)} "
                    f"loss={loss.item():.4f}",
                    flush=True,
                )

        val_y, val_score = score_dataset(
            model, tokenizer, tokenized["val"], train_cfg, device,
            batch_size_files, window_batch_size, use_amp,
        )
        val_metrics = evaluate(val_y, val_score)
        val_pr_auc = float(val_metrics["pr_auc"])
        improved = val_pr_auc > best_pr_auc
        if improved:
            best_pr_auc = val_pr_auc
            best_epoch = epoch
            bad_epochs = 0
            atomic_torch_save(best_path, {
                "model": model.state_dict(),
                "seed": seed,
                "best_epoch": best_epoch,
                "best_val_pr_auc": best_pr_auc,
                "run_fingerprint": fingerprint,
            })
        else:
            bad_epochs += 1
        history.append({
            "epoch": epoch + 1,
            "val_pr_auc": val_pr_auc,
            "val_f1_macro": float(val_metrics["f1_macro"]),
            "best": improved,
            "seconds": time.monotonic() - epoch_started,
        })
        atomic_torch_save(last_path, {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scaler": scaler.state_dict(),
            "epoch": epoch,
            "best_pr_auc": best_pr_auc,
            "best_epoch": best_epoch,
            "bad_epochs": bad_epochs,
            "history": history,
            "rng": rng_state(),
            "run_fingerprint": fingerprint,
        })
        print(
            f"  seed={seed} epoch={epoch + 1} val_PR-AUC={val_pr_auc:.6f} "
            f"best={best_pr_auc:.6f}@{best_epoch + 1} bad={bad_epochs}/{train_cfg['patience']}",
            flush=True,
        )
        if bad_epochs >= int(train_cfg["patience"]):
            break

    if not best_path.exists():
        raise RuntimeError(f"Seed {seed} did not produce a best checkpoint")
    best = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(best["model"])
    model.encoder.gradient_checkpointing_disable()
    result: dict = {
        "seed": seed,
        "best_epoch": int(best["best_epoch"]) + 1,
        "val_pr_auc": float(best["best_val_pr_auc"]),
        "elapsed_seconds": time.monotonic() - seed_started,
        "history": history,
        "run_fingerprint": fingerprint,
    }
    for split in ("test", "holdout"):
        y, score = score_dataset(
            model, tokenizer, tokenized[split], train_cfg, device,
            batch_size_files, window_batch_size, use_amp,
        )
        result[split] = evaluate(y, score)
    atomic_json(metrics_path, result)
    del model, optimizer, scaler
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return result


def aggregate_split(rows: list[dict], split: str) -> dict[str, list[float | None]]:
    if len(rows) == 1:
        return {metric: [float(rows[0][split][metric]), None] for metric in METRICS}
    aggregate = aggregate_seeds([{metric: row[split][metric] for metric in METRICS} for row in rows])
    return {
        metric: [
            float(aggregate[metric][0]),
            float(aggregate[metric][1]) if math.isfinite(float(aggregate[metric][1])) else None,
        ]
        for metric in METRICS
    }


def write_summary(path: Path, base: dict, completed: list[dict], status: str) -> None:
    summary = dict(base)
    summary["status"] = status
    summary["completed_seeds"] = [int(row["seed"]) for row in completed]
    summary["test"] = aggregate_split(completed, "test") if completed else {}
    summary["holdout"] = aggregate_split(completed, "holdout") if completed else {}
    summary["per_seed"] = [
        {
            "seed": int(row["seed"]),
            "best_epoch": int(row["best_epoch"]),
            "elapsed_seconds": float(row.get("elapsed_seconds", 0.0)),
            "val_pr_auc": float(row["val_pr_auc"]),
            "test": {metric: float(row["test"][metric]) for metric in METRICS},
            "holdout": {metric: float(row["holdout"][metric]) for metric in METRICS},
        }
        for row in completed
    ]
    atomic_json(path, summary)


def load_completed_seed(path: Path, seed: int, fingerprint: str) -> dict:
    result = json.loads(path.read_text())
    if result.get("seed") != seed or result.get("run_fingerprint") != fingerprint:
        raise RuntimeError(f"Seed {seed} result exists but is from a different run")
    for split in ("test", "holdout"):
        split_metrics = result.get(split)
        if not isinstance(split_metrics, dict) or any(
            metric not in split_metrics or not math.isfinite(float(split_metrics[metric]))
            for metric in METRICS
        ):
            raise RuntimeError(f"Seed {seed} result has missing or invalid {split} metrics")
    return result


def main(args) -> None:
    config_path = ROOT / args.config
    cfg = load_config(config_path, root=ROOT)
    train_cfg = cfg["codebert"]
    if str(train_cfg["model"]) != MODEL_NAME:
        raise ValueError(f"RQ1 CodeBERT must use {MODEL_NAME}, got {train_cfg['model']}")
    seeds = [int(seed) for seed in cfg["seeds"]]
    if len(seeds) != 5:
        raise ValueError(f"RQ1 CodeBERT requires exactly five configured seeds, got {seeds}")
    out_dir = ROOT / "experiments/runs/rq1_codebert"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = (out_dir / "run.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)
    print(f"Model: {MODEL_NAME}")
    print(f"Length strategy: {LENGTH_STRATEGY}")
    print(
        f"Windowing: max_length={train_cfg['max_length']}, stride={train_cfg['stride']} "
        f"(window-start advance), cap={train_cfg['max_windows_per_file']}, "
        "mean CodeBERT pooler_output per file"
    )

    rows_by_split, split_sizes = load_split_rows(cfg)
    input_path, input_digest = canonical_input_artifact(cfg, rows_by_split, out_dir)
    documents = load_canonical_documents(input_path)
    for split in SPLITS:
        expected = [row["sample_id"] for row in rows_by_split[split]]
        actual = [row["sample_id"] for row in documents[split]]
        if actual != expected:
            raise RuntimeError(f"Canonical artifact sample order differs from harness {split} split")

    hf_cache = ROOT / train_cfg["hf_cache"]
    hf_cache.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(hf_cache)
    os.environ["HF_HUB_CACHE"] = str(hf_cache / "hub")
    os.environ["TRANSFORMERS_CACHE"] = str(hf_cache / "transformers")
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    from transformers import AutoConfig, AutoModel, AutoTokenizer, __version__ as transformers_version

    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    if device.type == "cpu":
        print("WARNING: CodeBERT fine-tuning on CPU will be slow.", file=sys.stderr, flush=True)
    print(f"Loading {MODEL_NAME} into WorkingD-local cache {hf_cache}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_NAME, cache_dir=str(hf_cache), local_files_only=args.offline, use_fast=True
    )
    model_config = AutoConfig.from_pretrained(
        MODEL_NAME, cache_dir=str(hf_cache), local_files_only=args.offline
    )
    if model_config.model_type != "roberta" or model_config.hidden_size <= 0:
        raise RuntimeError(f"Unexpected CodeBERT encoder config: {model_config}")
    revision = getattr(model_config, "_commit_hash", None)
    tokenized = tokenize_documents(tokenizer, documents, train_cfg)
    window_counts = {
        split: {
            "files": len(tokenized[split]),
            "windows": sum(len(row["windows"]) for row in tokenized[split]),
            "files_with_8_windows": sum(
                len(row["windows"]) == int(train_cfg["max_windows_per_file"])
                for row in tokenized[split]
            ),
        }
        for split in SPLITS
    }

    run_identity = {
        "model": MODEL_NAME,
        "model_revision": revision,
        "transformers_version": transformers_version,
        "torch_version": torch.__version__,
        "input_sha256": input_digest,
        "config_sha256": sha256_file(config_path),
        "split_sizes": split_sizes,
        "seeds": seeds,
        "train_config": {key: value for key, value in train_cfg.items() if key != "hf_cache"},
    }
    fingerprint = hashlib.sha256(json.dumps(run_identity, sort_keys=True).encode()).hexdigest()
    base = {
        **run_identity,
        "n_seeds": len(seeds),
        "input_artifact": str(input_path.relative_to(ROOT)),
        "input_artifact_sha256": input_digest,
        "length_strategy": LENGTH_STRATEGY,
        "windowing_details": (
            "512 tokens including special tokens; window starts advance by 384 content tokens; "
            "first 8 windows retained; mean of CodeBERT pooler_output vectors per file"
        ),
        "train": {
            "optim": "adamw",
            "lr": float(train_cfg["lr"]),
            "weight_decay": float(train_cfg["weight_decay"]),
            "loss": "unweighted binary_cross_entropy_with_logits (same as harness neural baselines)",
            "select": "val_pr_auc+earlystop",
            "max_epochs": int(train_cfg["epochs"]),
            "patience": int(train_cfg["patience"]),
            "batch_size_files": int(train_cfg["batch_size_files"]),
            "window_batch_size": int(train_cfg["window_batch_size"]),
            "max_length": int(train_cfg["max_length"]),
            "stride": int(train_cfg["stride"]),
            "max_windows_per_file": int(train_cfg["max_windows_per_file"]),
            "gradient_checkpointing": bool(train_cfg["gradient_checkpointing"]),
            "class_counts": {
                split: {
                    "negative": sum(int(row["label"]) == 0 for row in documents[split]),
                    "positive": sum(int(row["label"]) == 1 for row in documents[split]),
                }
                for split in SPLITS
            },
            "window_counts": window_counts,
        },
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "run_fingerprint": fingerprint,
    }
    summary_path = out_dir / "codebert_rq1_summary.json"
    write_summary(summary_path, base, [], "running")

    completed: list[dict] = []
    for seed in seeds:
        metrics_path = out_dir / f"seed_{seed}" / "metrics.json"
        if metrics_path.exists():
            result = load_completed_seed(metrics_path, seed, fingerprint)
            print(f"  seed {seed}: already complete; reusing saved metrics", flush=True)
            completed.append(result)
    remaining = [seed for seed in seeds if seed not in {row["seed"] for row in completed}]
    auto = os.environ.get("AUTO") == "1"

    while remaining:
        seed = remaining.pop(0)
        set_seed(seed)
        try:
            encoder = AutoModel.from_pretrained(
                MODEL_NAME, cache_dir=str(hf_cache), local_files_only=args.offline
            )
            result = fit_seed(
                seed, tokenized, tokenizer, encoder, cfg, device,
                out_dir / f"seed_{seed}", fingerprint,
            )
            del encoder
        except KeyboardInterrupt:
            write_summary(summary_path, base, completed, "paused")
            print(f"\nInterrupted during seed {seed}; completed seeds were preserved.", flush=True)
            return

        completed.append(result)
        write_summary(summary_path, base, completed, "running" if remaining else "completed")
        print(f"seed {seed} xong, còn lại {remaining}", flush=True)
        if not remaining:
            print(f"All configured seeds complete; summary updated at {summary_path}", flush=True)
            break
        if auto:
            continue
        try:
            answer = input("Chạy tiếp seed kế? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            write_summary(summary_path, base, completed, "paused")
            print("\nPaused; completed seeds were preserved.", flush=True)
            return
        if answer.strip().lower() != "y":
            write_summary(summary_path, base, completed, "paused")
            print("Paused; completed seeds were preserved.", flush=True)
            return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/experiment/rq1_codebert.yaml")
    parser.add_argument("--offline", action="store_true", help="use only the WorkingD-local Hugging Face cache")
    parser.add_argument("--cpu", action="store_true", help="force CPU even if CUDA is available")
    main(parser.parse_args())
