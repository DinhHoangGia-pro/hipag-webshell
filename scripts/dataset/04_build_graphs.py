#!/usr/bin/env python3
import argparse

"""PHP -> đồ thị phân cấp (AST/CFG/DFG/call/include) -> PyG HeteroData. Resume + per-sample write."""


def main(cfg):
    pass  # TODO: gọi src.hipag.parsing + graph; shrink ra features_small


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    main(ap.parse_args())
