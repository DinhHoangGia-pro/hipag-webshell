"""Huấn luyện một seed (resume, per-epoch progress, num_workers — giống H-GNN).

Loss = BCE(phát hiện) + lambda_taint · BCE(cạnh taint yếu-giám-sát).
Chọn epoch tốt nhất theo `select_metric` trên val; early stopping theo `patience`.
τ của Taint-Dependency Predictor hiệu chỉnh trên val (tối đa F1 cạnh, ≥ tau_floor) sau MỖI epoch,
để các epoch sau train với đúng tập E_sem sẽ dùng lúc test.
Warmup (model.taint_predictor.warmup_epochs): các epoch đầu E_sem = cạnh luật; khi chuyển sang cạnh
học được thì best/patience được reset — chỉ chọn checkpoint ở chế độ sẽ dùng lúc suy luận.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from .data.collate import make_loader
from .eval import evaluate
from .graph.edges import SEM_NEG, SEM_POS
from .model.hipag import HiPaG
from .model.taint_predictor import calibrate_tau
from .utils.seed import set_seed

TRAIN_DEFAULTS = {
    "lr": 2e-4, "weight_decay": 1e-4, "epochs": 100, "batch_size": 32, "optimizer": "adamw",
    "lambda_taint": 0.5, "pos_weight": None, "grad_clip": 1.0, "patience": 15,
    "select_metric": "pr_auc", "threshold": 0.5, "num_workers": 0, "resume": True,
    "calibrate_tau": True,
}


@torch.no_grad()
def predict(model, loader, device) -> dict:
    """Trả y, score (P(webshell)), và xác suất cạnh taint trên SEM_POS/SEM_NEG (nếu có predictor)."""
    model.eval()
    ys, ss, tp, tl, n_sem, capf = [], [], [], [], [], []
    for b in loader:
        b = b.to(device)
        out = model(b)
        ys.append(b.y.cpu()); ss.append(torch.sigmoid(out["logit"]).cpu()); n_sem.append(out["n_sem"])
        capf.append(out["cand_capped_frac"])
        if model.taint is not None:
            for et, lab in ((SEM_POS, 1.0), (SEM_NEG, 0.0)):
                ei = b[et].edge_index
                if ei.numel():
                    tp.append(torch.sigmoid(model.taint(out["h0"], ei)).cpu())
                    tl.append(torch.full((ei.shape[1],), lab))
    cat = lambda xs: torch.cat(xs).numpy() if xs else np.empty(0)  # noqa: E731
    return {"y": cat(ys), "score": cat(ss), "taint_p": cat(tp), "taint_y": cat(tl),
            "n_sem_mean": float(np.mean(n_sem)) if n_sem else 0.0,
            "cand_capped_frac": float(np.mean(capf)) if capf else float("nan")}


def taint_edge_metrics(pred: dict, tau: float) -> dict:
    """F1/AUC của predictor so với nhãn yếu (chẩn đoán RQF-06; không phải metric phát hiện)."""
    p, y = pred["taint_p"], pred["taint_y"]
    if p.size == 0:
        return {}
    yhat = p > tau
    tp = float((yhat & (y > 0.5)).sum()); fp = float((yhat & (y <= 0.5)).sum()); fn = float((~yhat & (y > 0.5)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    out = {"taint_edge_f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0, "taint_tau": float(tau)}
    if 0 < y.sum() < y.size:
        from sklearn.metrics import roc_auc_score
        out["taint_edge_auc"] = float(roc_auc_score(y, p))
    return out


def _select_value(metrics: dict, key: str) -> float:
    v = metrics.get(key, math.nan)
    return metrics["f1_macro"] if v is None or math.isnan(v) else v


def train_one_seed(cfg: dict, seed: int, train_ds, val_ds, test_sets: dict, device: str = "cpu",
                   out_dir: str | None = None, log=print) -> dict:
    """Train một seed, trả {'seed','best_epoch','val','test': {tên: metrics}, 'scores': {...}, 'history'}.

    test_sets : {tên: dataset} — vd {'test': ..., 'holdout_mwf': ...} hoặc mỗi level obfuscation.
    out_dir   : nếu có, lưu last.pt mỗi epoch (resume được) + best.pt.
    """
    tc = {**TRAIN_DEFAULTS, **cfg.get("train", {})}
    set_seed(seed)
    model = HiPaG(cfg).to(device)
    if tc["optimizer"].lower() != "adamw":
        raise ValueError(f"optimizer chưa hỗ trợ: {tc['optimizer']}")
    opt = torch.optim.AdamW(model.parameters(), lr=float(tc["lr"]), weight_decay=float(tc["weight_decay"]))
    pw = None if tc["pos_weight"] is None else torch.tensor(float(tc["pos_weight"]), device=device)

    train_loader = make_loader(train_ds, tc["batch_size"], shuffle=True, num_workers=tc["num_workers"], seed=seed)
    val_loader = make_loader(val_ds, tc["batch_size"], num_workers=tc["num_workers"])

    start_epoch, best, best_state, best_tau, bad, history, best_epoch = 0, -math.inf, None, None, 0, [], -1
    best_mode = model.sem_mode
    ckpt_dir = Path(out_dir) if out_dir else None
    if ckpt_dir:
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        last = ckpt_dir / "last.pt"
        if tc["resume"] and last.exists():
            ck = torch.load(last, weights_only=False, map_location=device)
            model.load_state_dict(ck["model"]); opt.load_state_dict(ck["opt"])
            start_epoch, best, best_state, best_tau, bad, history, best_epoch = (
                ck["epoch"] + 1, ck["best"], ck["best_state"], ck["best_tau"], ck["bad"], ck["history"],
                ck["best_epoch"])
            best_mode = ck.get("best_mode", model.sem_mode)
            if model.taint is not None and ck.get("tau") is not None:
                model.taint.tau = ck["tau"]
            torch.set_rng_state(ck["rng_cpu"])
            log(f"[seed {seed}] resume từ epoch {start_epoch}")

    for epoch in range(start_epoch, int(tc["epochs"])):
        mode = model.set_epoch(epoch)
        if model.warmup_epochs and epoch == model.warmup_epochs:
            best, bad = -math.inf, 0          # vừa chuyển rule -> learned: không so với checkpoint warmup
            log(f"[seed {seed}] hết warmup: E_sem chuyển sang cạnh học được")
        if bad >= tc["patience"] and epoch >= model.warmup_epochs:
            break
        t0 = time.time()
        model.train()
        tot, tot_det, tot_taint, nb, capf = 0.0, 0.0, 0.0, 0, []
        for b in train_loader:
            b = b.to(device)
            out = model(b)
            det = F.binary_cross_entropy_with_logits(out["logit"], b.y, pos_weight=pw)
            loss = det + float(tc["lambda_taint"]) * out["taint_loss"]
            opt.zero_grad(set_to_none=True)
            loss.backward()
            if tc["grad_clip"]:
                torch.nn.utils.clip_grad_norm_(model.parameters(), float(tc["grad_clip"]))
            opt.step()
            tot += loss.item(); tot_det += det.item(); tot_taint += out["taint_loss"].item(); nb += 1
            capf.append(out["cand_capped_frac"])          # tỉ lệ đồ thị chạm max_cand, từng batch

        vp = predict(model, val_loader, device)
        if model.taint is not None and tc["calibrate_tau"] and vp["taint_p"].size:
            model.taint.tau = calibrate_tau(torch.from_numpy(vp["taint_p"]), torch.from_numpy(vp["taint_y"]),
                                            tau_floor=model.taint.tau_floor)
        vm = evaluate(vp["y"], vp["score"], tc["threshold"])
        vm.update(taint_edge_metrics(vp, model.taint.effective_tau if model.taint is not None else 0.5))
        sel = _select_value(vm, tc["select_metric"])
        improved = sel > best
        if improved:
            best, bad, best_epoch = sel, 0, epoch
            best_state = copy.deepcopy(model.state_dict())
            best_tau = model.taint.tau if model.taint is not None else None
            best_mode = mode
        else:
            bad += 1
        rec = {"epoch": epoch, "sem_mode": mode, "loss": tot / max(nb, 1), "loss_det": tot_det / max(nb, 1),
               "loss_taint": tot_taint / max(nb, 1), "val_" + tc["select_metric"]: sel,
               "val_f1_macro": vm["f1_macro"], "n_sem_val": vp["n_sem_mean"],
               "tau": best_tau if improved else (model.taint.tau if model.taint is not None else None),
               "cand_capped_frac": float(np.mean(capf)) if capf else math.nan,     # trung bình theo batch
               "cand_capped_max": float(np.max(capf)) if capf else math.nan,       # batch tệ nhất
               "sec": time.time() - t0}
        history.append(rec)
        log(f"[seed {seed}] ep {epoch:3d} [{mode:7s}] loss {rec['loss']:.4f} (det {rec['loss_det']:.4f} taint "
            f"{rec['loss_taint']:.4f}) val {tc['select_metric']} {sel:.4f} f1 {vm['f1_macro']:.4f} "
            f"|E_sem|/batch {vp['n_sem_mean']:.1f} max_cand-hit {rec['cand_capped_frac']:.2f}"
            f"(max {rec['cand_capped_max']:.2f}){' *' if improved else ''}")
        if ckpt_dir:
            torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "epoch": epoch, "best": best,
                        "best_state": best_state, "best_tau": best_tau, "bad": bad, "history": history, "best_epoch": best_epoch, "best_mode": best_mode,
                        "tau": model.taint.tau if model.taint is not None else None,
                        "rng_cpu": torch.get_rng_state()}, ckpt_dir / "last.pt")

    if best_state is None:
        raise RuntimeError("Không có epoch nào được train (epochs=0 hoặc resume từ run đã xong mà thiếu best_state)")
    model.load_state_dict(best_state)
    model.sem_mode = best_mode
    if model.taint is not None and best_tau is not None:
        model.taint.tau = best_tau
    if ckpt_dir:
        torch.save({"model": best_state, "tau": best_tau, "sem_mode": best_mode, "cfg": cfg, "seed": seed},
                   ckpt_dir / "best.pt")

    vp = predict(model, val_loader, device)
    res = {"seed": seed, "best_epoch": best_epoch, "sem_mode": best_mode,
           "val": {**evaluate(vp["y"], vp["score"], tc["threshold"]), **taint_edge_metrics(vp, model.taint.effective_tau if model.taint is not None else 0.5)},
           "test": {}, "scores": {}, "history": history}
    for name, ds in test_sets.items():
        tp_ = predict(model, make_loader(ds, tc["batch_size"], num_workers=tc["num_workers"]), device)
        res["test"][name] = {**evaluate(tp_["y"], tp_["score"], tc["threshold"]),
                             **taint_edge_metrics(tp_, model.taint.effective_tau if model.taint is not None else 0.5),
                             "n_sem_mean": tp_["n_sem_mean"], "cand_capped_frac": tp_["cand_capped_frac"]}
        res["scores"][name] = {"y": tp_["y"].tolist(), "score": tp_["score"].tolist()}
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Train một seed. Dùng scripts/run_experiment.py cho chạy N-seed.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--synthetic", action="store_true", help="smoke-test trên dữ liệu giả")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()
    from .utils.config import load_config
    cfg = load_config(args.config)
    if not args.synthetic:
        raise SystemExit("Chạy dữ liệu thật qua scripts/run_experiment.py (cần data/ + splits.csv).")
    from .data.synthetic import make_synthetic_dataset
    r = train_one_seed(cfg, args.seed, make_synthetic_dataset(64, 1), make_synthetic_dataset(32, 2),
                       {"test": make_synthetic_dataset(32, 3)}, args.device)
    print(json.dumps(r["test"], indent=1))
