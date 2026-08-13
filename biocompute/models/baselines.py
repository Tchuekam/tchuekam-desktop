"""Conventional baselines. These are the comparators biology must beat.

Deliberately simple and well-understood, so that any advantage attributed to a
biological substrate cannot be explained by a weak baseline.

NOT INCLUDED: RNN / LSTM. Those need PyTorch, which is a heavy dependency nothing
else here requires. `biocompute/models/reservoir.py` provides an echo-state network
as the recurrent/temporal comparator in pure numpy. If a gated recurrent baseline
is genuinely needed later, add it behind the same `Model` interface with torch in
its own extra -- do not add torch speculatively.
"""

from __future__ import annotations

import numpy as np

from biocompute.models.base import Model


class _SklearnModel(Model):
    """Shared plumbing: standardise features, then fit an sklearn estimator."""

    def __init__(self, **hyperparams):
        super().__init__(**hyperparams)
        self._pipe = None
        self._n_train = 0

    def _make_estimator(self):  # pragma: no cover - overridden
        raise NotImplementedError

    def fit(self, X, y):
        from sklearn.pipeline import Pipeline as SkPipeline
        from sklearn.preprocessing import StandardScaler

        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        self._n_train = len(y)
        self._pipe = SkPipeline(
            [("scale", StandardScaler()), ("clf", self._make_estimator())]
        )
        return self._timed_fit(lambda: self._pipe.fit(X, y))

    def predict(self, X):
        if self._pipe is None:
            raise RuntimeError(f"{self.name}: not fitted")
        return self._pipe.predict(np.asarray(X, dtype=np.float64))

    def _state(self):
        return {"_pipe": self._pipe, "_n_train": self._n_train,
                "_train_time_s": self._train_time_s}


class LogisticRegressionModel(_SklearnModel):
    name = "logistic_regression"

    def __init__(self, C: float = 1.0, max_iter: int = 2000, random_state: int = 0):
        super().__init__(C=C, max_iter=max_iter, random_state=random_state)

    def _make_estimator(self):
        from sklearn.linear_model import LogisticRegression

        return LogisticRegression(
            C=self.hyperparams["C"],
            max_iter=self.hyperparams["max_iter"],
            random_state=self.hyperparams["random_state"],
        )


class SVMModel(_SklearnModel):
    name = "svm_rbf"

    def __init__(self, C: float = 1.0, gamma: str = "scale", random_state: int = 0):
        super().__init__(C=C, gamma=gamma, random_state=random_state)

    def _make_estimator(self):
        from sklearn.svm import SVC

        return SVC(
            C=self.hyperparams["C"],
            gamma=self.hyperparams["gamma"],
            random_state=self.hyperparams["random_state"],
        )


class RandomForestModel(_SklearnModel):
    name = "random_forest"

    def __init__(self, n_estimators: int = 100, max_depth: int | None = None,
                 random_state: int = 0):
        super().__init__(n_estimators=n_estimators, max_depth=max_depth,
                         random_state=random_state)

    def _make_estimator(self):
        from sklearn.ensemble import RandomForestClassifier

        return RandomForestClassifier(
            n_estimators=self.hyperparams["n_estimators"],
            max_depth=self.hyperparams["max_depth"],
            random_state=self.hyperparams["random_state"],
            n_jobs=1,
        )


class MLPModel(_SklearnModel):
    name = "mlp"

    def __init__(self, hidden_layer_sizes: tuple = (64, 32), max_iter: int = 1000,
                 random_state: int = 0):
        super().__init__(hidden_layer_sizes=hidden_layer_sizes, max_iter=max_iter,
                         random_state=random_state)

    def _make_estimator(self):
        from sklearn.neural_network import MLPClassifier

        return MLPClassifier(
            hidden_layer_sizes=self.hyperparams["hidden_layer_sizes"],
            max_iter=self.hyperparams["max_iter"],
            random_state=self.hyperparams["random_state"],
        )


class MajorityClassModel(Model):
    """Predicts the most frequent training class. The floor every model must clear."""

    name = "majority_class"

    def __init__(self):
        super().__init__()
        self._majority = None
        self._n_train = 0

    def fit(self, X, y):
        y = np.asarray(y)
        self._n_train = len(y)

        def _f():
            vals, counts = np.unique(y, return_counts=True)
            self._majority = vals[counts.argmax()]

        return self._timed_fit(_f)

    def predict(self, X):
        return np.full(len(X), self._majority)


class TinyCNNModel(Model):
    """Small 2D CNN baseline for grid-shaped (visual) tasks.

    TWO HONESTY GUARDS, because this model can silently become something else:

    1. It needs PyTorch. Without it, this falls back to an sklearn MLP -- which is
       a DIFFERENT model. The fallback is recorded in `backend` and surfaced by
       `describe()`, so a benchmark row can never claim "tiny_cnn" while actually
       reporting an MLP.
    2. The conv path reshapes a flat feature vector into a square image, so it
       requires a perfect-square feature count. BioCompute's neural features are
       7 per channel (e.g. 56 for 8 channels), which is NOT square. On non-square
       input the CNN path is skipped rather than crashing on a bad `view()`.

    Check `model.backend` before quoting a result from this model.
    """

    name = "tiny_cnn"

    def __init__(self, epochs: int = 15, lr: float = 1e-3, batch_size: int = 32, random_state: int = 0):
        super().__init__(epochs=epochs, lr=lr, batch_size=batch_size, random_state=random_state)
        self.epochs = epochs
        self.lr = lr
        self.batch_size = batch_size
        self.random_state = random_state
        self._clf = None
        self.backend: str | None = None
        self.backend_reason: str | None = None
        self._side: int | None = None

    @staticmethod
    def _square_side(n_features: int) -> int | None:
        side = int(round(np.sqrt(n_features)))
        return side if side * side == n_features else None

    def describe(self) -> dict:
        return {
            **super().describe(),
            "backend": self.backend,
            "backend_reason": self.backend_reason,
            "is_actually_a_cnn": self.backend == "torch_cnn",
        }

    def fit(self, X, y):
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.int64)

        self._side = self._square_side(X.shape[1]) if X.ndim == 2 else 28
        use_cnn = self._side is not None
        if not use_cnn:
            self.backend_reason = (
                f"feature count {X.shape[1]} is not a perfect square, so it cannot be "
                f"reshaped into an image; CNN path skipped"
            )

        def _timed():
            try:
                if not use_cnn:
                    raise ImportError(self.backend_reason)
                import torch
                import torch.nn as nn
                import torch.optim as optim

                torch.manual_seed(self.random_state)
                side = self._side
                n_classes = len(np.unique(y))

                class Net(nn.Module):
                    def __init__(self):
                        super().__init__()
                        self.conv = nn.Sequential(
                            nn.Conv2d(1, 8, kernel_size=3, padding=1),
                            nn.ReLU(),
                            nn.MaxPool2d(2, 2),
                            nn.Conv2d(8, 16, kernel_size=3, padding=1),
                            nn.ReLU(),
                            nn.AdaptiveAvgPool2d((4, 4))
                        )
                        self.fc = nn.Linear(16 * 4 * 4, n_classes)

                    def forward(self, x):
                        if x.ndim == 2:
                            x = x.view(-1, 1, side, side)
                        feat = self.conv(x)
                        return self.fc(feat.view(feat.size(0), -1))

                model = Net()
                optimizer = optim.Adam(model.parameters(), lr=self.lr)
                criterion = nn.CrossEntropyLoss()

                X_t = torch.tensor(X, dtype=torch.float32)
                y_t = torch.tensor(y, dtype=torch.long)
                ds = torch.utils.data.TensorDataset(X_t, y_t)
                loader = torch.utils.data.DataLoader(ds, batch_size=self.batch_size, shuffle=True)

                model.train()
                for _ in range(self.epochs):
                    for bx, by in loader:
                        optimizer.zero_grad()
                        out = model(bx)
                        loss = criterion(out, by)
                        loss.backward()
                        optimizer.step()

                self._clf = model
                self.backend = "torch_cnn"
                self.backend_reason = "PyTorch available and features are square"
            except ImportError as e:
                from sklearn.neural_network import MLPClassifier

                self.backend = "sklearn_mlp_fallback"
                if self.backend_reason is None:
                    self.backend_reason = f"PyTorch unavailable ({e}); using sklearn MLP"
                clf = MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=200,
                                    random_state=self.random_state)
                clf.fit(X, y)
                self._clf = clf

        result = self._timed_fit(_timed)
        self.hyperparams["backend"] = self.backend
        self.hyperparams["backend_reason"] = self.backend_reason
        return result

    def predict(self, X):
        if self._clf is None:
            raise RuntimeError(f"{self.name}: not fitted")
        X = np.asarray(X, dtype=np.float32)
        if self.backend == "torch_cnn":
            import torch

            self._clf.eval()
            with torch.no_grad():
                side = int(np.sqrt(X.shape[1])) if X.ndim == 2 else 28
                out = self._clf(torch.tensor(X, dtype=torch.float32).view(-1, 1, side, side))
                return out.argmax(dim=1).detach().cpu().numpy()
        return self._clf.predict(X)


DEFAULT_BASELINES = [
    MajorityClassModel,
    LogisticRegressionModel,
    SVMModel,
    RandomForestModel,
    MLPModel,
    TinyCNNModel,
]

