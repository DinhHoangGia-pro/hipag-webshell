#!/usr/bin/env python3
import argparse

"""Split cluster-disjoint theo group (RQF-05). MWF tách hẳn làm cross-dataset holdout."""


def main(cfg):
    pass  # TODO: GroupShuffleSplit theo cluster_id, stratify label/source


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
