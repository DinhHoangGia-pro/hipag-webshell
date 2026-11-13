#!/usr/bin/env python3
"""Run PASS_B §17(c) inference and nodeobf continuation without writing paper files."""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.ensemble import RandomForestClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from hipag.data.collate import make_loader  # noqa: E402
from hipag.data.dataset import WebshellGraphDataset  # noqa: E402
from hipag.eval import evaluate  # noqa: E402
from hipag.graph.edges import STMT  # noqa: E402
from hipag.model.hipag import HiPaG  # noqa: E402
from hipag.train import predict, train_one_seed  # noqa: E402
from hipag.utils.config import load_config  # noqa: E402
from scripts.run_baselines import (  # noqa: E402
    FlatGATv2,
    SequenceDataset,
    TokenBiLSTM,
    canonical_source_bytes,
    graph_loader,
    neural_scores,
    read_csv,
    sequence_loader,
)
from scripts.run_codebert_baseline import (  # noqa: E402
    CodeBertClassifier,
    score_dataset,
    tokenize_documents,
)

LEVELS = ("L1", "L2", "L3", "L4", "L5")
ALL_LEVELS = ("L0", *LEVELS)
SEEDS = (0, 1, 2, 3, 4)
CODEBERT_SPLITS = ("train", "val", "test", "holdout")
PRIMARY_METRICS = ("pr_auc", "f1_macro")
BOOTSTRAP_METRICS = (
    "f1_macro", "accuracy", "precision", "recall", "mcc", "pr_auc",
    "fpr_at_tpr95", "prec_at_base_10pct", "prec_at_base_1pct", "prec_at_base_0p1pct",
)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False, default=float) + "\n")
    tmp.replace(path)


def read_output(path: Path, phase: str) -> dict:
    if not path.exists():
        return {"schema_version": 1, "phase": phase, "records": []}
    out = json.loads(path.read_text())
    if out.get("phase") != phase:
        raise RuntimeError(f"Existing output {path} belongs to phase {out.get('phase')!r}")
    return out


def checked_dataset(cfg: dict, split: str, where: dict | None = None) -> WebshellGraphDataset:
    dc = cfg.get("data", {})
    ds = WebshellGraphDataset(
        str(ROOT / cfg["splits"]),
        str(ROOT / dc.get("features_dir", "data/features_small")),
        split=split,
        where=where,
        max_bytes=int(dc.get("max_bytes", 10 * 1024 * 1024)),
    )
    if not len(ds):
        raise RuntimeError(f"Empty dataset: split={split}, where={where}")
    if ds.skipped:
        raise RuntimeError(f"Dataset split={split}, where={where} skipped {len(ds.skipped)} files")
    labels = set(ds.labels)
    if labels != {0, 1}:
        raise RuntimeError(f"Dataset split={split}, where={where} has labels {sorted(labels)}")
    return ds


def graph_prediction(model, ds, device: str, batch_size: int = 32) -> tuple[np.ndarray, np.ndarray]:
    pred = predict(model, make_loader(ds, batch_size=batch_size), device)
    expected = np.asarray(ds.labels, dtype=np.int64)
    if not np.array_equal(expected, pred["y"].astype(np.int64)):
        raise RuntimeError("Graph inference labels do not match split CSV row order")
    return expected, pred["score"]


def append_records(path: Path, output: dict, new_records: list[dict]) -> None:
    keys = {(r["model"], int(r["seed"]), r["level"]) for r in output["records"]}
    for row in new_records:
        key = (row["model"], int(row["seed"]), row["level"])
        if key not in keys:
            output["records"].append(row)
            keys.add(key)
    atomic_json(path, output)


def aggregate_records(records: list[dict], group_fields: tuple[str, ...]) -> dict:
    groups: dict[tuple, list[dict]] = {}
    for row in records:
        groups.setdefault(tuple(row[field] for field in group_fields), []).append(row)
    summary = {}
    for key, rows in groups.items():
        name = "/".join(map(str, key))
        metrics = {}
        for metric in PRIMARY_METRICS:
            values = [float(r[metric]) for r in rows if math.isfinite(float(r[metric]))]
            metrics[metric] = {
                "mean": float(np.mean(values)) if values else None,
                "sd": float(np.std(values, ddof=1)) if len(values) > 1 else (0.0 if values else None),
                "n_seeds": len(values),
            }
        summary[name] = metrics
    return summary


def load_level_datasets(config_path: str, levels=LEVELS) -> tuple[dict, dict[str, WebshellGraphDataset]]:
    cfg = load_config(config_path, root=ROOT)
    datasets = {level: checked_dataset(cfg, "obf", {"level": level}) for level in levels}
    return cfg, datasets


def load_codebert(cfg: dict, seed: int, device: torch.device):
    from transformers import AutoModel, AutoTokenizer

    cc = cfg["codebert"]
    model_name = cc["model"]
    cache_dir = str(ROOT / cc["hf_cache"])
    tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir, local_files_only=True)
    encoder = AutoModel.from_pretrained(model_name, cache_dir=cache_dir, local_files_only=True)
    model = CodeBertClassifier(encoder, int(encoder.config.hidden_size)).to(device)
    checkpoint_path = ROOT / "experiments/runs/rq1_codebert" / f"seed_{seed}" / "best.pt"
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    if int(checkpoint.get("seed", -1)) != seed:
        raise RuntimeError(f"CodeBERT checkpoint seed mismatch: {checkpoint_path}")
    model.load_state_dict(checkpoint["model"], strict=True)
    return tokenizer, model


def codebert_predict(model, tokenizer, rows: list[dict], cfg: dict, device: torch.device):
    cc = cfg["codebert"]
    labels, scores = score_dataset(
        model, tokenizer, rows, cc, device,
        batch_size_files=int(cc["batch_size_files"]),
        window_batch_size=int(cc["window_batch_size"]),
        use_amp=device.type == "cuda",
    )
    expected = np.asarray([int(r["label"]) for r in rows], dtype=np.int64)
    if not np.array_equal(expected, labels):
        raise RuntimeError("CodeBERT scores are not aligned with canonical input rows")
    return labels, scores


def tokenize_codebert_rows(tokenizer, rows: list[dict], cfg: dict) -> list[dict]:
    documents = {split: [] for split in CODEBERT_SPLITS}
    documents["test"] = rows
    return tokenize_documents(tokenizer, documents, cfg["codebert"])["test"]


def obfuscation_sources(level_datasets: dict[str, WebshellGraphDataset], cfg: dict) -> dict[str, list[dict]]:
    from scripts.metadata_probe import shallow_features, graphmeta_features
    from hipag.parsing.php_ast import canonicalize_batch

    obf_manifest_path = ROOT / "experiments/dataset/obfuscation_manifest.csv"
    obf_manifest = {r["sample_id"]: r for r in read_csv(obf_manifest_path)}
    all_rows = [r for level in LEVELS for r in level_datasets[level].rows]
    paths = []
    for row in all_rows:
        entry = obf_manifest.get(row["sample_id"])
        if entry is None:
            raise RuntimeError(f"No obfuscation manifest row for {row['sample_id']}")
        paths.append(ROOT / entry["php_path"])
    canonical = canonicalize_batch(paths)
    if len(canonical) != len(paths):
        raise RuntimeError(f"Canonicalizer returned {len(canonical)} rows for {len(paths)} files")
    import base64

    by_id = {}
    for row, encoded, path in zip(all_rows, canonical, paths):
        raw = base64.b64decode(encoded) if encoded else path.read_bytes()
        by_id[row["sample_id"]] = {
            "canonical_text": raw.decode("utf-8", "replace"),
            "shallow": shallow_features(raw),
        }

    log_path = ROOT / "data/features_small/_build_log_obf.jsonl"
    obf_stats = {}
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                item = json.loads(line)
                obf_stats[item["sample_id"]] = item
    if len(obf_stats) < len(all_rows):
        raise RuntimeError(f"Obfuscation graph metadata incomplete: {len(obf_stats)}/{len(all_rows)}")
    for sample_id, item in by_id.items():
        item["graphmeta"] = graphmeta_features(obf_stats[sample_id])

    return {
        level: [
            {
                "sample_id": row["sample_id"],
                "label": int(float(row["label"])),
                "canonical_text": by_id[row["sample_id"]]["canonical_text"],
                "shallow": by_id[row["sample_id"]]["shallow"],
                "graphmeta": by_id[row["sample_id"]]["graphmeta"],
            }
            for row in level_datasets[level].rows
        ]
        for level in LEVELS
    }


def run_c1(device_name: str) -> Path:
    path = ROOT / "experiments/runs/pass_b_c1/c1_obfuscation_matrix.json"
    output = read_output(path, "c1")
    record_keys = [(r["model"], int(r["seed"]), r["level"]) for r in output["records"]]
    if len(record_keys) != len(set(record_keys)):
        raise RuntimeError(f"Duplicate model/seed/level rows in existing c1 output: {path}")
    cfg, graph_sets = load_level_datasets("configs/experiment/rq1_baselines.yaml")
    codebert_cfg = load_config("configs/experiment/rq1_codebert.yaml", root=ROOT)
    sources = obfuscation_sources(graph_sets, cfg)
    splits = read_csv(ROOT / cfg["splits"])
    train_rows = [r for r in splits if r["split"] == "train"]
    train_raw = canonical_source_bytes(cfg, train_rows)
    from scripts.metadata_probe import shallow_features, graphmeta_features

    stats = {r["sample_id"]: r for r in read_csv(ROOT / cfg["graph_stats"])}
    X_train = {
        "shallow": np.asarray([shallow_features(raw) for raw in train_raw], dtype=np.float32),
        "graphmeta": np.asarray([graphmeta_features(stats[r["sample_id"]]) for r in train_rows],
                                dtype=np.float32),
    }
    y_train = np.asarray([int(r["label"]) for r in train_rows], dtype=np.int64)
    device = torch.device(device_name)

    existing = {(r["model"], int(r["seed"]), r["level"]) for r in output["records"]}
    for probe in ("shallow", "graphmeta"):
        for seed in SEEDS:
            pending = [level for level in LEVELS if (probe, seed, level) not in existing]
            if not pending:
                continue
            forest = RandomForestClassifier(
                n_estimators=int(cfg["baselines"]["random_forest_estimators"]),
                random_state=seed, n_jobs=-1, class_weight="balanced",
            )
            forest.fit(X_train[probe], y_train)
            new = []
            for level in pending:
                rows = sources[level]
                X = np.asarray([r[probe] for r in rows], dtype=np.float32)
                y = np.asarray([r["label"] for r in rows], dtype=np.int64)
                class_index = np.flatnonzero(forest.classes_ == 1)
                if class_index.size != 1:
                    raise RuntimeError(f"{probe} seed {seed}: trained forest lacks positive class")
                score = forest.predict_proba(X)[:, int(class_index[0])]
                m = evaluate(y, score)
                new.append({"model": probe, "seed": seed, "level": level, "n": len(y),
                            "pr_auc": m["pr_auc"], "f1_macro": m["f1_macro"]})
            append_records(path, output, new)
            existing.update((r["model"], int(r["seed"]), r["level"]) for r in new)
            print(f"[c1] {probe} seed {seed} complete", flush=True)

    # The neural baselines and CodeBERT use only the saved best checkpoints.
    for model_name in ("bilstm", "flat_gatv2"):
        for seed in SEEDS:
            pending = [level for level in LEVELS if (model_name, seed, level) not in existing]
            if not pending:
                continue
            ckpt_path = ROOT / f"experiments/runs/rq1_baselines/{model_name}/seed_{seed}/best.pt"
            checkpoint = torch.load(ckpt_path, map_location="cpu", weights_only=False)
            if model_name == "bilstm":
                sequence_cfg = cfg["baselines"]["sequence"]
                model = TokenBiLSTM(sequence_cfg["embedding_dim"], sequence_cfg["hidden_dim"]).to(device)
                ds_by_level = {level: SequenceDataset(graph_sets[level]) for level in pending}
                loader_fn = lambda ds: sequence_loader(ds, int(cfg["baselines"]["neural"]["batch_size"]))
                kind = "bilstm"
            else:
                node_dim = int(graph_sets[pending[0]][0][STMT].x.shape[1])
                model = FlatGATv2(node_dim, **cfg["baselines"]["flat_gatv2"]).to(device)
                ds_by_level = {level: graph_sets[level] for level in pending}
                loader_fn = lambda ds: graph_loader(ds, int(cfg["baselines"]["neural"]["batch_size"]))
                kind = "flat_gatv2"
            model.load_state_dict(checkpoint["state_dict"], strict=True)
            model.eval()
            for level, ds in ds_by_level.items():
                y, score = neural_scores(model, loader_fn(ds), kind, device)
                if not np.array_equal(y.astype(int), np.asarray(graph_sets[level].labels)):
                    raise RuntimeError(f"{model_name} seed {seed} label order mismatch at {level}")
                m = evaluate(y, score)
                record = {"model": model_name, "seed": seed, "level": level, "n": len(y),
                          "pr_auc": m["pr_auc"], "f1_macro": m["f1_macro"]}
                append_records(path, output, [record])
                existing.add((model_name, seed, level))
                print(f"[c1] {model_name} seed {seed} {level} complete", flush=True)
            del model

    for seed in SEEDS:
        pending = [level for level in LEVELS if ("codebert", seed, level) not in existing]
        if not pending:
            continue
        tokenizer, model = load_codebert(codebert_cfg, seed, device)
        for level in pending:
            docs = [
                {"sample_id": row["sample_id"], "label": row["label"],
                 "canonical_text": row["canonical_text"]}
                for row in sources[level]
            ]
            tokenized = tokenize_codebert_rows(tokenizer, docs, codebert_cfg)
            y, score = codebert_predict(model, tokenizer, tokenized, codebert_cfg, device)
            m = evaluate(y, score)
            record = {"model": "codebert", "seed": seed, "level": level, "n": len(y),
                      "pr_auc": m["pr_auc"], "f1_macro": m["f1_macro"]}
            append_records(path, output, [record])
            existing.add(("codebert", seed, level))
            print(f"[c1] codebert seed {seed} {level} complete", flush=True)
        del model, tokenizer
        if device.type == "cuda":
            torch.cuda.empty_cache()

    expected = {(model, seed, level)
                for model in ("shallow", "graphmeta", "bilstm", "flat_gatv2", "codebert")
                for seed in SEEDS for level in LEVELS}
    actual = {(r["model"], int(r["seed"]), r["level"]) for r in output["records"]}
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise RuntimeError(
            f"c1 coverage mismatch: {len(actual)}/{len(expected)}; "
            f"missing={missing[:10]}, unexpected={unexpected[:10]}"
        )
    output["aggregation"] = aggregate_records(output["records"], ("model", "level"))
    output["protocol"] = {
        "metric_names": ["pr_auc", "f1_macro"],
        "model_source": "saved RQ1 best.pt; shallow/graphmeta RF refit on fixed train split",
        "obfuscation_levels": list(LEVELS),
        "seeds": list(SEEDS),
        "canonical_input": "tools/php/canonicalize.php via canonicalize_batch; same shallow-probe canonicalization",
        "graph_feature_dir": "data/features_small (deobfuscation-on graph features)",
    }
    atomic_json(path, output)
    return path


def run_c3(device_name: str) -> Path:
    path = ROOT / "experiments/runs/pass_b_c3/c3_ablation_obfuscation_matrix.json"
    output = read_output(path, "c3")
    base_cfg, graph_sets = load_level_datasets("configs/experiment/rq4_ablation.yaml")
    variants = ("full", "rule_e_sem", "no_token_transformer", "no_e_sem", "no_e_dfg",
                "no_inter_transformer", "no_global_features", "pool_mean")
    device = torch.device(device_name)
    existing = {(r["model"], int(r["seed"]), r["level"]) for r in output["records"]}
    for variant in variants:
        cfg = copy.deepcopy(base_cfg)
        cfg["model"]["ablation"] = variant
        for seed in SEEDS:
            pending = [level for level in LEVELS if (variant, seed, level) not in existing]
            if not pending:
                continue
            ckpt_path = ROOT / f"experiments/runs/rq4_ablation/{variant}/seed_{seed}/best.pt"
            checkpoint = torch.load(ckpt_path, map_location="cpu", weights_only=False)
            model = HiPaG(cfg).to(device)
            model.load_state_dict(checkpoint["model"], strict=True)
            model.sem_mode = checkpoint.get("sem_mode", model.sem_mode)
            if model.taint is not None and checkpoint.get("tau") is not None:
                model.taint.tau = float(checkpoint["tau"])
            new = []
            for level in pending:
                ds = graph_sets[level]
                y, score = graph_prediction(model, ds, device_name, int(cfg["train"]["batch_size"]))
                metrics = evaluate(y, score)
                new.append({"model": variant, "seed": seed, "level": level, "n": len(y),
                            **{key: float(metrics[key]) for key in BOOTSTRAP_METRICS}})
            del model
            append_records(path, output, new)
            existing.update((r["model"], int(r["seed"]), r["level"]) for r in new)
            print(f"[c3] {variant} seed {seed} complete", flush=True)
    expected = {(v, seed, level) for v in variants for seed in SEEDS for level in LEVELS}
    actual = {(r["model"], int(r["seed"]), r["level"]) for r in output["records"]}
    if actual != expected:
        raise RuntimeError(f"c3 coverage mismatch: {len(actual)}/{len(expected)}")
    output["aggregation"] = aggregate_records(output["records"], ("model", "level"))
    output["protocol"] = {
        "metrics": list(BOOTSTRAP_METRICS), "variants": list(variants),
        "levels": list(LEVELS), "seeds": list(SEEDS),
        "checkpoint_source": "experiments/runs/rq4_ablation/<variant>/seed_<seed>/best.pt",
    }
    atomic_json(path, output)
    return path


def canonical_rows_from_artifact(path: Path) -> dict[str, list[dict]]:
    docs = {"test": [], "holdout": []}
    with path.open(encoding="utf-8") as handle:
        metadata = json.loads(handle.readline())
        if "_metadata" not in metadata:
            raise RuntimeError(f"Missing canonical input metadata: {path}")
        for line in handle:
            row = json.loads(line)
            if row["split"] in docs:
                docs[row["split"]].append(row)
    return docs


def run_c4(device_name: str, n_boot: int) -> Path:
    path = ROOT / "experiments/runs/pass_b_c4/c4_per_file_bootstrap.json"
    output = read_output(path, "c4")
    cfg = load_config("configs/experiment/rq1_baselines.yaml", root=ROOT)
    cb_cfg = load_config("configs/experiment/rq1_codebert.yaml", root=ROOT)
    device = torch.device(device_name)
    datasets = {
        split: checked_dataset(cfg, split)
        for split in ("test", "holdout")
    }
    for split, ds in datasets.items():
        keyset = {r["sample_id"] for r in ds.rows}
        if len(keyset) != len(ds):
            raise RuntimeError(f"Duplicate sample IDs in c4 {split}")

    # One entry per model/split; per-seed scores are retained for paired bootstrap.
    for model_name in ("bilstm", "flat_gatv2", "codebert"):
        for split, ds in datasets.items():
            key = f"{model_name}/{split}"
            existing_entry = output.get("datasets", {}).get(key, {})
            saved_seeds = {int(s) for s in existing_entry.get("scores_by_seed", {})}
            pending = [seed for seed in SEEDS if seed not in saved_seeds]
            if not pending:
                continue
            if model_name == "codebert":
                canonical_path = ROOT / "experiments/runs/rq1_codebert/canonical_inputs.jsonl"
                code_docs = canonical_rows_from_artifact(canonical_path)[split]
                expected_ids = [r["sample_id"] for r in ds.rows]
                by_id = {r["sample_id"]: r for r in code_docs}
                if set(by_id) != set(expected_ids):
                    raise RuntimeError(f"Canonical CodeBERT artifact IDs differ from c4 {split}")
                ordered_docs = [by_id[sid] for sid in expected_ids]
                tokenizer, model = load_codebert(cb_cfg, pending[0], device)
                files = tokenize_codebert_rows(tokenizer, ordered_docs, cb_cfg)
                for seed in pending:
                    if seed != pending[0]:
                        checkpoint = torch.load(
                            ROOT / f"experiments/runs/rq1_codebert/seed_{seed}/best.pt",
                            map_location=device, weights_only=False,
                        )
                        model.load_state_dict(checkpoint["model"], strict=True)
                    y, score = codebert_predict(model, tokenizer, files, cb_cfg, device)
                    if not np.array_equal(y, np.asarray(ds.labels)):
                        raise RuntimeError(f"CodeBERT label order differs from c4 {split}")
                    existing_entry.setdefault("scores_by_seed", {})[str(seed)] = score.tolist()
                    existing_entry["sample_ids"] = [r["sample_id"] for r in ds.rows]
                    existing_entry["labels"] = y.tolist()
                    output.setdefault("datasets", {})[key] = existing_entry
                    atomic_json(path, output)
                    print(f"[c4] codebert {split} seed {seed} complete", flush=True)
                del model, tokenizer
                if device.type == "cuda":
                    torch.cuda.empty_cache()
                continue

            for seed in pending:
                checkpoint = torch.load(
                    ROOT / f"experiments/runs/rq1_baselines/{model_name}/seed_{seed}/best.pt",
                    map_location="cpu", weights_only=False,
                )
                if model_name == "bilstm":
                    sequence_cfg = cfg["baselines"]["sequence"]
                    model = TokenBiLSTM(sequence_cfg["embedding_dim"], sequence_cfg["hidden_dim"]).to(device)
                    eval_ds = SequenceDataset(ds)
                    loader = sequence_loader(eval_ds, int(cfg["baselines"]["neural"]["batch_size"]))
                    kind = "bilstm"
                else:
                    model = FlatGATv2(int(ds[0][STMT].x.shape[1]),
                                      **cfg["baselines"]["flat_gatv2"]).to(device)
                    loader = graph_loader(ds, int(cfg["baselines"]["neural"]["batch_size"]))
                    kind = "flat_gatv2"
                model.load_state_dict(checkpoint["state_dict"], strict=True)
                y, score = neural_scores(model, loader, kind, device)
                if not np.array_equal(y.astype(int), np.asarray(ds.labels)):
                    raise RuntimeError(f"{model_name} label order differs from c4 {split}")
                existing_entry.setdefault("scores_by_seed", {})[str(seed)] = score.tolist()
                existing_entry["sample_ids"] = [r["sample_id"] for r in ds.rows]
                existing_entry["labels"] = y.astype(int).tolist()
                output.setdefault("datasets", {})[key] = existing_entry
                del model
                atomic_json(path, output)
                print(f"[c4] {model_name} {split} seed {seed} complete", flush=True)

    for model_name in ("bilstm", "flat_gatv2", "codebert"):
        for split, ds in datasets.items():
            key = f"{model_name}/{split}"
            entry = output["datasets"][key]
            seed_scores = entry["scores_by_seed"]
            if set(map(int, seed_scores)) != set(SEEDS):
                raise RuntimeError(f"c4 seed coverage incomplete: {key}")
            if (
                entry.get("bootstrap_replicates") == n_boot
                and "mean_seed_metric_bootstrap_ci" in entry
            ):
                continue
            y = np.asarray(entry["labels"], dtype=np.int64)
            scores = np.asarray([seed_scores[str(seed)] for seed in SEEDS], dtype=np.float64)
            seed_metrics = {
                str(seed): evaluate(y, scores[i])
                for i, seed in enumerate(SEEDS)
            }
            progress = entry.get("_bootstrap_progress")
            if progress and progress.get("n_bootstrap") == n_boot:
                rng = np.random.default_rng()
                rng.bit_generator.state = progress["rng_state"]
                done = int(progress["done"])
                boot = progress["samples"]
            else:
                rng = np.random.default_rng(20261113 + sum(map(ord, key)))
                done = 0
                boot = {metric: [] for metric in BOOTSTRAP_METRICS}
            class_indices = [np.flatnonzero(y == label) for label in (0, 1)]
            for iteration in range(done, n_boot):
                idx = np.concatenate([
                    rng.choice(indices, size=len(indices), replace=True) for indices in class_indices
                ])
                for metric in BOOTSTRAP_METRICS:
                    values = [float(evaluate(y[idx], scores[i, idx])[metric]) for i in range(len(SEEDS))]
                    values = [v for v in values if math.isfinite(v)]
                    if values:
                        boot[metric].append(float(np.mean(values)))
                if (iteration + 1) % 100 == 0 or iteration + 1 == n_boot:
                    entry["_bootstrap_progress"] = {
                        "n_bootstrap": n_boot,
                        "done": iteration + 1,
                        "rng_state": rng.bit_generator.state,
                        "samples": boot,
                    }
                    output["datasets"][key] = entry
                    atomic_json(path, output)
            entry["seed_metrics"] = seed_metrics
            entry["mean_seed_metric_bootstrap_ci"] = {
                metric: {
                    "percentile_95_ci": [float(np.percentile(values, 2.5)),
                                          float(np.percentile(values, 97.5))],
                    "bootstrap_mean": float(np.mean(values)),
                    "n_bootstrap": len(values),
                    "sampling_unit": "file; stratified by label; same resample shared across five seeds",
                }
                for metric, values in boot.items() if values
            }
            entry["bootstrap_replicates"] = n_boot
            entry.pop("_bootstrap_progress", None)
            entry["mean_seed_per_file_score"] = scores.mean(axis=0).tolist()
            atomic_json(path, output)
    output["protocol"] = {
        "metrics": list(BOOTSTRAP_METRICS),
        "bootstrap_replicates": n_boot,
        "sampling": "stratified file bootstrap; each replicate resamples positives/negatives within label",
        "per_file_scores": "retained for each seed; also include five-seed mean score",
        "splits": ["test", "holdout"],
    }
    atomic_json(path, output)
    return path


def run_c2(device_name: str) -> Path:
    path = ROOT / "experiments/runs/pass_b_c2/c2_nodeobf_obfuscation_matrix.json"
    output = read_output(path, "c2")
    output.setdefault("records", [])
    cfg = load_config("configs/experiment/rq2_obfuscation_nodeobf.yaml", root=ROOT)
    cfg.setdefault("model", {})["ablation"] = "full"
    train_ds = checked_dataset(cfg, "train")
    val_ds = checked_dataset(cfg, "val")
    level_sets = {
        level: checked_dataset(cfg, "obf", {"level": level})
        for level in ALL_LEVELS
    }
    device = torch.device(device_name)

    def valid_training_marker(result: dict, seed: int) -> bool:
        if int(result.get("seed", -1)) != seed or "best_epoch" not in result:
            return False
        return isinstance(result.get("val"), dict) and isinstance(result.get("test"), dict)

    def has_complete_inference(result: dict, seed: int) -> bool:
        if not valid_training_marker(result, seed):
            return False
        if not isinstance(result.get("scores"), dict):
            return False
        for level, ds in level_sets.items():
            name = f"obf_off_{level}"
            if name not in result["test"] or name not in result["scores"]:
                return False
            if not {"pr_auc", "f1_macro"}.issubset(result["test"][name]):
                return False
            scores = result["scores"][name]
            if len(scores.get("y", [])) != len(ds) or len(scores.get("score", [])) != len(ds):
                return False
            if scores["y"] != ds.labels:
                return False
        return True

    def add_seed_records(seed: int, result: dict) -> None:
        records = [row for row in output["records"] if int(row["seed"]) != seed]
        for level in ALL_LEVELS:
            metrics = result["test"][f"obf_off_{level}"]
            records.append({
                "model": "hipag_nodeobf",
                "seed": seed,
                "level": level,
                "n": int(metrics["n"]),
                "f1_macro": float(metrics["f1_macro"]),
                "pr_auc": float(metrics["pr_auc"]),
            })
        output["records"] = records
        atomic_json(path, output)

    for seed in SEEDS:
        seed_metrics_path = ROOT / f"experiments/runs/rq4_ablation_nodeobf/full/seed_{seed}.json"
        ckpt_dir = ROOT / f"experiments/runs/rq4_ablation_nodeobf/full/seed_{seed}"
        if seed_metrics_path.exists():
            saved = json.loads(seed_metrics_path.read_text())
        else:
            saved = None

        if saved is not None and seed == 0 and valid_training_marker(saved, seed):
            ckpt_path = ckpt_dir / "best.pt"
            if not ckpt_path.exists():
                raise RuntimeError(f"Seed 0 has a metrics marker but no checkpoint: {ckpt_path}")
            if not has_complete_inference(saved, seed):
                checkpoint = torch.load(ckpt_path, map_location="cpu", weights_only=False)
                model = HiPaG(cfg).to(device)
                model.load_state_dict(checkpoint["model"], strict=True)
                model.sem_mode = checkpoint.get("sem_mode", model.sem_mode)
                if model.taint is not None and checkpoint.get("tau") is not None:
                    model.taint.tau = float(checkpoint["tau"])
                saved.setdefault("scores", {})
                for level, ds in level_sets.items():
                    name = f"obf_off_{level}"
                    y, score = graph_prediction(model, ds, device_name, int(cfg["train"]["batch_size"]))
                    saved.setdefault("test", {})[name] = evaluate(y, score)
                    saved["scores"][name] = {"y": y.tolist(), "score": score.tolist()}
                del model
                saved["sample_ids"] = {
                    level: [row["sample_id"] for row in ds.rows]
                    for level, ds in level_sets.items()
                }
                saved["checkpoint_source"] = str((ckpt_dir / "best.pt").relative_to(ROOT))
                atomic_json(seed_metrics_path, saved)
            add_seed_records(seed, saved)
            print("[c2] seed 0 training reused; L0-L5 inference complete", flush=True)
            continue

        if (saved is not None and has_complete_inference(saved, seed)
                and (ckpt_dir / "best.pt").exists()):
            add_seed_records(seed, saved)
            print(f"[c2] seed {seed} valid metrics/checkpoint marker; skipped", flush=True)
            continue

        test_sets = {f"obf_off_{level}": ds for level, ds in level_sets.items()}
        result = train_one_seed(
            cfg, seed, train_ds, val_ds, test_sets,
            device=device_name, out_dir=str(ckpt_dir), log=print,
        )
        result["sample_ids"] = {
            level: [row["sample_id"] for row in ds.rows]
            for level, ds in level_sets.items()
        }
        result["checkpoint_source"] = str((ckpt_dir / "best.pt").relative_to(ROOT))
        if not has_complete_inference(result, seed):
            raise RuntimeError(f"Seed {seed} did not produce complete per-level inference")
        atomic_json(seed_metrics_path, result)
        add_seed_records(seed, result)
        print(f"[c2] seed {seed} train+L0-L5 inference complete", flush=True)

    expected = {(seed, level) for seed in SEEDS for level in ALL_LEVELS}
    actual = {(int(row["seed"]), row["level"]) for row in output["records"]}
    if actual != expected:
        raise RuntimeError("c2 seed coverage incomplete")
    summary = {}
    for level in ALL_LEVELS:
        summary[level] = {}
        for metric in PRIMARY_METRICS:
            values = [
                float(next(row[metric] for row in output["records"]
                           if int(row["seed"]) == seed and row["level"] == level))
                for seed in SEEDS
            ]
            summary[level][metric] = {
                "mean": float(np.mean(values)),
                "sd": float(np.std(values, ddof=1)),
                "n_seeds": len(values),
            }
    output["aggregation"] = summary
    output["protocol"] = {
        "model": "HiPaG full, deobfuscation disabled",
        "levels": list(ALL_LEVELS), "seeds": list(SEEDS),
        "metrics": list(PRIMARY_METRICS),
        "config": "configs/experiment/rq2_obfuscation_nodeobf.yaml",
        "seed_completion_marker": "experiments/runs/rq4_ablation_nodeobf/full/seed_<k>.json",
        "seed_outputs": "per-seed metrics and scores are stored beside their checkpoints",
        "resume": "completed seeds are skipped by valid per-seed JSON marker; an in-progress seed resumes from last.pt",
    }
    atomic_json(path, output)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("c1", "c3", "c4", "c2"), required=True)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--bootstrap", type=int, default=2000)
    args = parser.parse_args()
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    if args.phase == "c1":
        result = run_c1(args.device)
    elif args.phase == "c3":
        result = run_c3(args.device)
    elif args.phase == "c4":
        result = run_c4(args.device, args.bootstrap)
    else:
        result = run_c2(args.device)
    print(f"[{args.phase}] complete: {result.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
