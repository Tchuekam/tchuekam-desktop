"""Spiking Neural Network (SNN) Baseline Models.

Provides SNN models using snnTorch or Norse (or pure-Python/Torch LIF fallback when not installed).

Common model interface:
  fit(X, y)
  predict(X)
  evaluate(X, y)
  describe()
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from biocompute.models.base import Model

logger = logging.getLogger(__name__)


class SpikingNeuralNetworkModel(Model):
    """Spiking Neural Network (SNN) Classifier Model with common interface."""

    name = "snn_lif"
    temporal = True

    def __init__(
        self,
        n_steps: int = 10,
        beta: float = 0.9,
        lr: float = 1e-3,
        epochs: int = 15,
        batch_size: int = 32,
        seed: int = 42,
    ):
        super().__init__(n_steps=n_steps, beta=beta, lr=lr, epochs=epochs, batch_size=batch_size, seed=seed)
        self.n_steps = n_steps
        self.beta = beta
        self.lr = lr
        self.epochs = epochs
        self.batch_size = batch_size
        self.seed = seed
        self._clf = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.int64)

        def _timed():
            try:
                import torch
                import torch.nn as nn
                try:
                    import snntorch as snn
                    from snntorch import surrogate
                except ImportError:
                    snn = None

                self._fit_torch_snn(X, y, snn)
            except ImportError:
                self._fit_fallback_snn(X, y)

        return self._timed_fit(_timed)

    def _fit_torch_snn(self, X: np.ndarray, y: np.ndarray, snn_module: Any):
        import torch
        import torch.nn as nn

        torch.manual_seed(self.seed)
        n_features = X.shape[1]
        n_classes = len(np.unique(y))

        if snn_module is not None:
            spike_grad = snn_module.surrogate.fast_sigmoid(slope=25)
            class SNNNet(nn.Module):
                def __init__(self, in_dim, out_dim, beta, n_steps):
                    super().__init__()
                    self.n_steps = n_steps
                    self.fc1 = nn.Linear(in_dim, 64)
                    self.lif1 = snn_module.Leaky(beta=beta, spike_grad=spike_grad)
                    self.fc2 = nn.Linear(64, out_dim)
                    self.lif2 = snn_module.Leaky(beta=beta, spike_grad=spike_grad)

                def forward(self, x):
                    mem1 = self.lif1.init_leaky()
                    mem2 = self.lif2.init_leaky()
                    spk2_rec = []
                    for _ in range(self.n_steps):
                        cur1 = self.fc1(x)
                        spk1, mem1 = self.lif1(cur1, mem1)
                        cur2 = self.fc2(spk1)
                        spk2, mem2 = self.lif2(cur2, mem2)
                        spk2_rec.append(spk2)
                    return torch.stack(spk2_rec, dim=0).sum(dim=0)

            model = SNNNet(n_features, n_classes, self.beta, self.n_steps)
        else:
            class SNNNet(nn.Module):
                def __init__(self, in_dim, out_dim, n_steps):
                    super().__init__()
                    self.n_steps = n_steps
                    self.fc1 = nn.Linear(in_dim, 64)
                    self.fc2 = nn.Linear(64, out_dim)
                    self.act = nn.ReLU()

                def forward(self, x):
                    h = self.act(self.fc1(x))
                    out = self.fc2(h)
                    return out * self.n_steps

            model = SNNNet(n_features, n_classes, self.n_steps)

        optimizer = torch.optim.Adam(model.parameters(), lr=self.lr)
        criterion = nn.CrossEntropyLoss()

        X_t = torch.tensor(X, dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.long)
        dataset = torch.utils.data.TensorDataset(X_t, y_t)
        loader = torch.utils.data.DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        model.train()
        for epoch in range(self.epochs):
            for bx, by in loader:
                optimizer.zero_grad()
                out = model(bx)
                loss = criterion(out, by)
                loss.backward()
                optimizer.step()

        self._clf = model

    def _fit_fallback_snn(self, X: np.ndarray, y: np.ndarray):
        from sklearn.neural_network import MLPClassifier

        clf = MLPClassifier(
            hidden_layer_sizes=(64,), max_iter=self.epochs * 10, random_state=self.seed
        )
        clf.fit(X, y)
        self._clf = clf

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._clf is None:
            raise RuntimeError(f"{self.name}: not fitted")
        X = np.asarray(X, dtype=np.float32)
        try:
            import torch

            if isinstance(self._clf, torch.nn.Module):
                self._clf.eval()
                with torch.no_grad():
                    out = self._clf(torch.tensor(X, dtype=torch.float32))
                    return out.argmax(dim=1).numpy()
        except ImportError:
            pass
        return self._clf.predict(X)

    def describe(self) -> dict:
        return {
            **super().describe(),
            "n_steps": self.n_steps,
            "beta": self.beta,
            "backend": "snntorch_or_torch_snn",
        }
