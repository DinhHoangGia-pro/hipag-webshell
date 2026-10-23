"""Learned Taint-Dependency Predictor (RQF-06) — thay 9-cặp luật cứng bằng link-prediction.

Spec cần điền (T0.4 trong kế hoạch):
  P(e_sem_ij=1) = sigmoid(MLP([h_i || h_j]))
  weak supervision: positive = cặp (source, sink) khớp seed trong cửa sổ CFG/DFG;
                    negative = cặp không khớp, lấy mẫu đều.  Loss = BCE.  Hiệu chỉnh tau trên val.

VỎ.
"""
import torch.nn as nn


class TaintDependencyPredictor(nn.Module):
    def __init__(self, d_in: int, mlp_hidden: int = 128, tau: float = 0.5):
        super().__init__()
        self.tau = tau
        # TODO: MLP([h_i||h_j]) -> logit

    def edge_logit(self, h_i, h_j):
        raise NotImplementedError  # TODO

    def predict_edges(self, h, candidate_pairs):
        raise NotImplementedError  # TODO: trả cạnh có P>tau

    def weak_labels_from_seeds(self, graph):
        raise NotImplementedError  # TODO(RQF-06)

    def sample_negatives(self, graph, n):
        raise NotImplementedError  # TODO(RQF-06)

    def calibrate_tau(self, val_loader):
        raise NotImplementedError  # TODO(RQF-03/06)
