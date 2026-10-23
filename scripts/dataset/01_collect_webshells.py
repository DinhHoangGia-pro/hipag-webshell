#!/usr/bin/env python3
import argparse

"""Thu thập + gộp nhãn webshell từ 5 tập (configs/dataset/collect.yaml). Ghi manifest."""


def main(cfg):
    pass  # TODO: duyệt webshell_sources, lọc PHP, ghi experiments/dataset/manifest_raw.csv


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
