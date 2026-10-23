#!/usr/bin/env python3
import argparse

"""Leakage/shortcut probe (chuẩn nhóm, RQF-04/05): chỉ dùng đặc trưng nông/metadata
(độ dài file, entropy, tỉ lệ ký tự, có-chuỗi-base64...) -> RandomForest, group-CV theo cluster.
Nếu AUC cao bất thường => dataset có shortcut, phải sửa trước khi tin model."""
from sklearn.ensemble import RandomForestClassifier  # noqa


def main(cfg):
    pass  # TODO: trích metadata features; GroupKFold theo cluster_id; báo acc/auc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
