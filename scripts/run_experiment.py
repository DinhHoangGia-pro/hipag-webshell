#!/usr/bin/env python3
import argparse

"""Chạy một RQ với N seed, gộp mean±sd, xuất numbers.tex (RQF-07/09)."""
import yaml


def main(args):
    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    # TODO: for seed in cfg['seeds']: train_one_seed; eval; gộp mean±sd; write_numbers_tex
    print("TODO run:", cfg)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--seeds", type=int, default=5)
    main(ap.parse_args())
