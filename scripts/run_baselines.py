#!/usr/bin/env python3
"""Fit same-split baselines and evaluate existing HiPaG checkpoints on test/holdout."""
from __future__ import annotations

import argparse
import copy
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.ensemble import RandomForestClassifier
from torch.nn.utils.rnn import pack_padded_sequence, pad_sequence
from torch.utils.data import DataLoader, Dataset, Subset
from torch_geometric.nn import GATv2Conv, global_max_pool, global_mean_pool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from hipag.data.collate import make_loader  # noqa: E402
from hipag.data.dataset import WebshellGraphDataset  # noqa: E402
from hipag.eval import evaluate, write_numbers_tex  # noqa: E402
from hipag.graph.edges import PYG_EDGE, STMT  # noqa: E402
from hipag.model.hipag import HiPaG  # noqa: E402
from hipag.parsing.php_ast import canonicalize_batch  # noqa: E402
from hipag.train import predict  # noqa: E402
from hipag.utils.config import load_config  # noqa: E402
from hipag.utils.metrics import aggregate_seeds, format_mean_sd  # noqa: E402

METRICS = [
    "f1_macro", "accuracy", "precision", "recall", "mcc", "pr_auc",
    "fpr_at_tpr95", "prec_at_base_10pct", "prec_at_base_1pct", "prec_at_base_0p1pct",
]
BASELINE_CAVEATS = {
    "opcode_cnn": "Not run: PHP VLD/opcode dumper is unavailable in this environment; source-token CNN is not an opcode baseline.",
    "codes": "Bi-LSTM is the requested non-pretrained sequence alternative; CodeBERT was not downloaded or evaluated.",
    "glareshell": "Not reproduced: the paper's implementation, manually assigned risk dictionary, and matching graph preprocessing are not available locally. rule_e_sem is not a GlareShell reproduction.",
    "yara": "Not run: no YARA executable or pinned PHP-webshell ruleset is installed/provided.",
    "holdout": "OOD holdout webshells come from c01dsnap, a distinct source collection but the same broad PHP-webshell family as training; this is not cross-family or cross-language generalization.",
}


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def read_csv(path: Path) -> list[dict]:
    import csv
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def limited_indices(labels, limit: int) -> list[int]:
    groups = {label: [i for i, value in enumerate(labels) if int(value) == label] for label in (0, 1)}
    per_class = min(limit // 2, min(map(len, groups.values())))
    selected = groups[0][:per_class] + groups[1][:per_class]
    if len(selected) < limit:
        selected_set = set(selected)
        remaining = [i for i in range(len(labels)) if i not in selected_set]
        selected.extend(remaining[:limit - len(selected)])
    return sorted(selected)


def limited_rows(rows: list[dict], limit: int) -> list[dict]:
    indices = limited_indices([int(row["label"]) for row in rows], min(len(rows), limit))
    return [rows[i] for i in indices]


class SequenceDataset(Dataset):
    def __init__(self, graphs: Dataset, limit: int | None = None):
        self.samples = []
        size = len(graphs) if limit is None else min(len(graphs), limit)
        for i in range(size):
            graph = graphs[i]
            tokens = graph[STMT].x_tok.reshape(-1)
            tokens = tokens[tokens != 0][:512]
            if tokens.numel() == 0:
                tokens = torch.ones(1, dtype=torch.long)
            self.samples.append((tokens.long(), graph.y.reshape(-1).float()))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        return self.samples[index]


def collate_sequences(rows):
    seqs, ys = zip(*rows)
    lengths = torch.tensor([len(s) for s in seqs], dtype=torch.long)
    return pad_sequence(seqs, batch_first=True, padding_value=0), lengths, torch.cat(ys)


class TokenBiLSTM(nn.Module):
    def __init__(self, embedding_dim: int = 64, hidden_dim: int = 96):
        super().__init__()
        self.embedding = nn.Embedding(4096, embedding_dim, padding_idx=0)
        self.encoder = nn.LSTM(embedding_dim, hidden_dim, batch_first=True, bidirectional=True)
        self.head = nn.Sequential(nn.Dropout(0.25), nn.Linear(hidden_dim * 2, 1))

    def forward(self, tokens, lengths):
        emb = self.embedding(tokens)
        packed = pack_padded_sequence(emb, lengths.cpu(), batch_first=True, enforce_sorted=False)
        _, (hidden, _) = self.encoder(packed)
        return self.head(torch.cat((hidden[-2], hidden[-1]), dim=1)).reshape(-1)


class FlatGATv2(nn.Module):
    """Statement-level flat GATv2 over sequence/skip/CFG/DFG edges; no E_sem or hierarchy."""
    EDGE_NAMES = ("E_seq", "E_skip", "E_cfg", "E_dfg")

    def __init__(self, node_dim: int, hidden_dim: int = 64, heads: int = 2, layers: int = 2):
        super().__init__()
        self.token_embedding = nn.Embedding(4096, 32, padding_idx=0)
        self.input = nn.Linear(node_dim + 32, hidden_dim)
        self.convs = nn.ModuleList(
            GATv2Conv(hidden_dim, hidden_dim // heads, heads=heads, edge_dim=len(self.EDGE_NAMES),
                      add_self_loops=True, dropout=0.1)
            for _ in range(layers)
        )
        self.norms = nn.ModuleList(nn.LayerNorm(hidden_dim) for _ in range(layers))
        self.dropout = nn.Dropout(0.1)
        self.head = nn.Sequential(nn.Linear(hidden_dim * 2, hidden_dim), nn.ReLU(),
                                  nn.Dropout(0.2), nn.Linear(hidden_dim, 1))

    def forward(self, batch):
        store = batch[STMT]
        tok = self.token_embedding(store.x_tok)
        mask = store.x_tok.ne(0).unsqueeze(-1)
        tok = (tok * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1)
        h = torch.relu(self.input(torch.cat((store.x, tok), dim=1)))
        edge_indices, edge_attrs = [], []
        for i, name in enumerate(self.EDGE_NAMES):
            ei = batch[PYG_EDGE[name]].edge_index
            edge_indices.append(ei)
            attr = h.new_zeros((ei.shape[1], len(self.EDGE_NAMES)))
            if ei.shape[1]:
                attr[:, i] = 1.0
            edge_attrs.append(attr)
        edge_index = torch.cat(edge_indices, dim=1)
        edge_attr = torch.cat(edge_attrs, dim=0)
        for conv, norm in zip(self.convs, self.norms):
            h = norm(h + self.dropout(torch.nn.functional.elu(conv(h, edge_index, edge_attr))))
        graph_batch = store.batch
        pooled = torch.cat((global_mean_pool(h, graph_batch), global_max_pool(h, graph_batch)), dim=1)
        return self.head(pooled).reshape(-1)


def graph_loader(ds, batch_size, shuffle=False, seed=None):
    return make_loader(ds, batch_size=batch_size, shuffle=shuffle, seed=seed)


def sequence_loader(ds, batch_size, shuffle=False, seed=None):
    generator = None
    if seed is not None:
        generator = torch.Generator().manual_seed(seed)
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle, generator=generator,
                      collate_fn=collate_sequences)


def model_output(model, batch, kind, device):
    if kind == "bilstm":
        tokens, lengths, labels = batch
        return model(tokens.to(device), lengths), labels.to(device)
    batch = batch.to(device)
    return model(batch), batch.y.reshape(-1).float()


@torch.no_grad()
def neural_scores(model, loader, kind, device):
    model.eval()
    ys, scores = [], []
    for batch in loader:
        logits, y = model_output(model, batch, kind, device)
        ys.extend(y.detach().cpu().numpy().tolist())
        scores.extend(torch.sigmoid(logits).detach().cpu().numpy().tolist())
    return np.asarray(ys), np.asarray(scores)


def fit_neural(kind, train_ds, val_ds, eval_sets, cfg, seed, device, out_dir):
    set_seed(seed)
    neural_cfg = cfg["baselines"]["neural"]
    seq_cfg = cfg["baselines"]["sequence"]
    gat_cfg = cfg["baselines"]["flat_gatv2"]
    if kind == "bilstm":
        train_ds = SequenceDataset(train_ds)
        val_ds = SequenceDataset(val_ds)
        train_loader = sequence_loader(train_ds, neural_cfg["batch_size"], True, seed)
        val_loader = sequence_loader(val_ds, neural_cfg["batch_size"])
        model = TokenBiLSTM(seq_cfg["embedding_dim"], seq_cfg["hidden_dim"])
    else:
        train_loader = graph_loader(train_ds, neural_cfg["batch_size"], True, seed)
        val_loader = graph_loader(val_ds, neural_cfg["batch_size"])
        model = FlatGATv2(train_ds[0][STMT].x.shape[1], **gat_cfg)
    model = model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=neural_cfg["lr"],
                                  weight_decay=neural_cfg["weight_decay"])
    best_metric, best_state, best_epoch, bad = -math.inf, None, -1, 0
    for epoch in range(int(neural_cfg["epochs"])):
        model.train()
        for batch in train_loader:
            logits, y = model_output(model, batch, kind, device)
            loss = nn.functional.binary_cross_entropy_with_logits(logits, y)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        val_y, val_score = neural_scores(model, val_loader, kind, device)
        val_metric = evaluate(val_y, val_score)["pr_auc"]
        if val_metric > best_metric:
            best_metric, best_epoch, bad = val_metric, epoch, 0
            best_state = copy.deepcopy(model.state_dict())
        else:
            bad += 1
        print(f"    [{kind}] seed={seed} epoch={epoch + 1} val_PR-AUC={val_metric:.4f}", flush=True)
        if bad >= int(neural_cfg["patience"]):
            break
    if best_state is None:
        raise RuntimeError(f"{kind} seed {seed}: training did not produce a validation checkpoint")
    model.load_state_dict(best_state)
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": best_state, "best_epoch": best_epoch, "seed": seed, "kind": kind},
               out_dir / "best.pt")
    result = {"seed": seed, "best_epoch": best_epoch, "val_pr_auc": best_metric, "test": {}, "holdout": {}}
    for split, dataset in eval_sets.items():
        if kind == "bilstm":
            dataset = SequenceDataset(dataset)
            loader = sequence_loader(dataset, neural_cfg["batch_size"])
        else:
            loader = graph_loader(dataset, neural_cfg["batch_size"])
        y, score = neural_scores(model, loader, kind, device)
        result[split] = evaluate(y, score)
    del model, optimizer
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return result


def source_features(cfg, split_rows):
    manifest = {r["sample_id"]: r for r in read_csv(ROOT / cfg["manifest"])}
    stats = {r["sample_id"]: r for r in read_csv(ROOT / cfg["graph_stats"])}
    paths = [ROOT / manifest[r["sample_id"]]["path"] for r in split_rows]
    canonical = canonicalize_batch(paths)
    from scripts.metadata_probe import graphmeta_features, shallow_features
    import base64
    raw_bytes = [base64.b64decode(b64) if b64 else p.read_bytes() for b64, p in zip(canonical, paths)]
    return {
        "shallow": np.asarray([shallow_features(b) for b in raw_bytes], dtype=np.float32),
        "graphmeta": np.asarray([graphmeta_features(stats[r["sample_id"]]) for r in split_rows],
                                dtype=np.float32),
    }


def fit_forest(X_train, y_train, eval_matrices, seeds, estimators, name, out_dir):
    seed_results = []
    for seed in seeds:
        model = RandomForestClassifier(n_estimators=estimators, random_state=seed,
                                       n_jobs=-1, class_weight="balanced")
        model.fit(X_train, y_train)
        result = {"seed": seed}
        for split, (X, y) in eval_matrices.items():
            probabilities = model.predict_proba(X)
            positive_index = np.flatnonzero(model.classes_ == 1)
            score = probabilities[:, positive_index[0]] if positive_index.size else np.zeros(len(X))
            result[split] = evaluate(y, score)
        seed_results.append(result)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"seed_{seed}.json").write_text(json.dumps(result, indent=2))
        print(f"  [{name}] seed {seed} complete", flush=True)
    return seed_results


def aggregate_results(results, splits):
    out = {}
    for split in splits:
        out[split] = aggregate_seeds([r[split] for r in results])
    return out


def markdown_report(results, split_names, caveats, n_seeds):
    lines = [f"# Same-split baselines ({n_seeds} seeds; mean ± sample SD)",
             "", "Metrics except MCC are percentages; MCC is on [-1, 1].",
             "Dataset split is fixed by `experiments/dataset/splits.csv`; all fitted baselines train only on `train`.",
             ""]
    metrics = METRICS
    for split in split_names:
        lines += [f"## {split}", "", "| Model | " + " | ".join(metrics) + " |",
                  "|---|" + "---:|" * len(metrics)]
        for name, result in results.items():
            agg = result[split]
            vals = [format_mean_sd(*agg[m], scale=1 if m == "mcc" else 100,
                                   digits=3 if m == "mcc" else 2) for m in metrics]
            lines.append("| " + name + " | " + " | ".join(vals) + " |")
    lines += ["", "## Not run / interpretation limits", ""]
    lines.extend(f"- **{k}:** {v}" for k, v in caveats.items())
    lines += ["", "- `graphmeta` and `shallow` are leakage/shortcut baselines, not semantic competitors.",
              "- The flat GATv2 and hashed parser-token Bi-LSTM are local controlled baselines, not claims of reproducing named papers."]
    return "\n".join(lines) + "\n"


def main(args):
    cfg = load_config(args.config, root=ROOT)
    if args.epochs is not None:
        cfg["baselines"]["neural"]["epochs"] = args.epochs
        cfg["baselines"]["neural"]["patience"] = min(args.epochs, cfg["baselines"]["neural"]["patience"])
    seeds = list(cfg["seeds"])
    splits_path = ROOT / cfg["splits"]
    feature_dir = ROOT / cfg["features_dir"]
    limit = args.max_samples
    datasets = {}
    for split in ("train", "val", "test", "holdout"):
        ds = WebshellGraphDataset(str(splits_path), str(feature_dir), split=split)
        if limit is not None:
            ds = Subset(ds, limited_indices(ds.labels, min(len(ds), limit)))
        if len(ds) == 0:
            raise SystemExit(f"Empty split {split}")
        datasets[split] = ds
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(args.out) if args.out else ROOT / "experiments/runs/rq1_baselines"
    out_dir.mkdir(parents=True, exist_ok=True)
    chosen = args.models or ["shallow", "graphmeta", "bilstm", "flat_gatv2", "hipag_full"]
    results_by_name, per_seed = {}, {}

    if "shallow" in chosen or "graphmeta" in chosen:
        split_rows = read_csv(splits_path)
        split_rows = [r for r in split_rows if r["split"] in ("train", "test", "holdout")]
        if limit is not None:
            split_rows = [
                row for split in ("train", "test", "holdout")
                for row in limited_rows([x for x in split_rows if x["split"] == split], limit)
            ]
        feature_sets = source_features(cfg, split_rows)
        labels = np.asarray([int(r["label"]) for r in split_rows])
        split_labels = np.asarray([r["split"] for r in split_rows])
        for name in ("shallow", "graphmeta"):
            if name not in chosen:
                continue
            X = feature_sets[name]
            train_mask = split_labels == "train"
            eval_matrices = {
                split: (X[split_labels == split], labels[split_labels == split])
                for split in ("test", "holdout")
            }
            seeds_results = fit_forest(
                X[train_mask], labels[train_mask], eval_matrices, seeds,
                cfg["baselines"]["random_forest_estimators"], name, out_dir / name,
            )
            per_seed[name] = seeds_results
            results_by_name[name] = aggregate_results(seeds_results, ("test", "holdout"))

    eval_sets = {"test": datasets["test"], "holdout": datasets["holdout"]}
    if "bilstm" in chosen or "flat_gatv2" in chosen:
        for name in ("bilstm", "flat_gatv2"):
            if name not in chosen:
                continue
            seed_results = []
            for seed in seeds:
                f = out_dir / name / f"seed_{seed}.json"
                if f.exists():
                    result = json.loads(f.read_text())
                    print(f"  [{name}] seed {seed}: resume from result JSON", flush=True)
                else:
                    result = fit_neural(name, datasets["train"], datasets["val"], eval_sets, cfg,
                                        seed, device, out_dir / name / f"seed_{seed}")
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text(json.dumps(result, indent=2, default=float))
                seed_results.append(result)
            per_seed[name] = seed_results
            results_by_name[name] = aggregate_results(seed_results, ("test", "holdout"))

    hipag_results = {"test": [], "holdout": []}
    if "hipag_full" in chosen:
        for seed in seeds:
            ck_path = ROOT / f"experiments/runs/rq4_ablation/full/seed_{seed}/best.pt"
            ck = torch.load(ck_path, map_location=device, weights_only=False)
            model = HiPaG(ck["cfg"]).to(device)
            model.load_state_dict(ck["model"])
            model.sem_mode = ck.get("sem_mode", model.sem_mode)
            if model.taint is not None and ck.get("tau") is not None:
                model.taint.tau = ck["tau"]
            for split in ("test", "holdout"):
                p = predict(model, graph_loader(datasets[split], 32), device)
                hipag_results[split].append(evaluate(p["y"], p["score"]))
            del model, ck
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        per_seed["HiPaG_full"] = [
            {"seed": seed, "test": hipag_results["test"][i], "holdout": hipag_results["holdout"][i]}
            for i, seed in enumerate(seeds)
        ]
        results_by_name["HiPaG(full)"] = aggregate_results(per_seed["HiPaG_full"], ("test", "holdout"))

    summaries = {
        "config": args.config, "seeds": seeds, "device": device,
        "trained_models": chosen, "train_sizes": {k: len(v) for k, v in datasets.items()},
        "metrics": METRICS, "results": results_by_name, "per_seed": per_seed,
        "caveats": BASELINE_CAVEATS,
    }
    (out_dir / "summary.json").write_text(json.dumps(summaries, indent=2, default=float))
    split_names = ("test", "holdout")
    (out_dir / "summary.md").write_text(markdown_report(results_by_name, split_names, BASELINE_CAVEATS, len(seeds)))
    print((out_dir / "summary.md").read_text())

    if args.max_samples is None:
        tex = ROOT / cfg["report"]["write_numbers_tex"]
        aliases = {"f1_macro": "Fone", "pr_auc": "PRAUC", "fpr_at_tpr95": "FPR"}
        for name, result in results_by_name.items():
            prefix = "HiPaG" if name == "HiPaG(full)" else "RqOne" + "".join(
                part.title().replace("_", "") for part in name.replace("(", "_").replace(")", "").split("_")
            )
            for split in split_names:
                write_numbers_tex(result[split], str(tex), prefix=prefix + split.title(),
                                  metrics=METRICS, n_seeds=len(seeds))
            if name == "HiPaG(full)":
                write_numbers_tex(result["test"], str(tex), prefix="HiPaG", metrics=METRICS,
                                  n_seeds=len(seeds), metric_name_aliases=aliases)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/experiment/rq1_baselines.yaml")
    parser.add_argument("--models", nargs="*", choices=["shallow", "graphmeta", "bilstm", "flat_gatv2", "hipag_full"])
    parser.add_argument("--device")
    parser.add_argument("--out")
    parser.add_argument("--max-samples", type=int, help="smoke test only; never writes paper macros")
    parser.add_argument("--epochs", type=int, help="override neural epochs for smoke tests")
    main(parser.parse_args())
