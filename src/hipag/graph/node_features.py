"""Đặc trưng nút: loại AST/opcode + cờ source/sink/decode + entropy cục bộ + positional. VỎ."""
from __future__ import annotations


def shannon_entropy(s: str) -> float:
    raise NotImplementedError  # TODO


def node_vector(node) -> list:
    raise NotImplementedError  # TODO: one-hot loại node + cờ ngữ nghĩa + entropy + positional
