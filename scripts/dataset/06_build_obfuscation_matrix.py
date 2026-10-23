#!/usr/bin/env python3
import argparse

"""Sinh ma trận obfuscation held-out (RQ2/K2): biến đổi giữ-ngữ-nghĩa webshell test theo level L0..L5.
KHÔNG dùng để train — chỉ đo kháng obfuscation phân tầng."""


def main(cfg):
    pass  # TODO: áp từng level; lưu kèm level_id để phân tầng


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
