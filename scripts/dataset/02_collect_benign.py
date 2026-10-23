#!/usr/bin/env python3
import argparse

"""Lấy mẫu benign + subset 'hard benign' (framework dùng call_user_func) — RQF-04. Ghi nhãn + tỉ lệ lớp."""


def main(cfg):
    pass  # TODO: thủ tục lấy mẫu minh bạch; báo class ratio


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
