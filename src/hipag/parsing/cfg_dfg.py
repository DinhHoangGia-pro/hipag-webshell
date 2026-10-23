"""Dựng CFG + DFG trong hàm từ AST. TODO: def-use cho biến, source/sink tagging."""
from __future__ import annotations


def build_cfg(ast: dict):
    """Control-flow graph mức basic-block. TODO."""
    raise NotImplementedError


def build_dfg(ast: dict):
    """Data-flow (def->use) trong hàm. TODO."""
    raise NotImplementedError
