"""Common model interface: fit / predict / evaluate / save / load.

Every model reports the same metric block so biological and conventional
approaches can be compared under identical conditions.

ENERGY AND COST ARE EXPLICITLY NULLABLE. `energy_joules` and `cost_usd` default to
None and stay None unless something actually measured them. They are never
estimated, extrapolated, or filled from a vendor claim. A None here means
"not measured", which is a valid and honest benchmark result.
"""

from __future__ import annotations

import json
import pickle
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


@dataclass
class ModelMetrics:
    """Standard metric block. Shared by every model in every benchmark."""

    accuracy: float
    precision_macro: float
    recall_macro: float
    f1_macro: float
    confusion_matrix: list[list[int]]
    n_train: int
    n_test: int
    n_classes: int
    n_features: int
    train_time_s: float
    inference_time_s: float
    inference_time_per_sample_ms: float
    chance_accuracy: float
    #: Filled only by an actual measurement. Never estimated.
    energy_joules: float | None = None
    #: Filled only by an actual measurement. Never estimated.
    cost_usd: float | None = None
    #: Set by evaluation.permutation_test() when it is run.
    permutation_p_value: float | None = None
    permutation_null_mean: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Model(ABC):
    """Base class for every decoder/classifier in the benchmark."""

    name: str = "unnamed"
    #: Set True by models that consume raw/temporal input rather than flat features.
    temporal: bool = False

    def __init__(self, **hyperparams):
        self.hyperparams = hyperparams
        self._fitted = False
        self._train_time_s = 0.0

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> Model: ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray: ...

    def evaluate(self, X: np.ndarray, y: np.ndarray) -> ModelMetrics:
        from sklearn.metrics import (
            accuracy_score,
            confusion_matrix,
            precision_recall_fscore_support,
        )

        if not self._fitted:
            raise RuntimeError(f"{self.name}: fit() before evaluate()")

        t0 = time.perf_counter()
        pred = self.predict(X)
        infer_s = time.perf_counter() - t0

        p, r, f1, _ = precision_recall_fscore_support(
            y, pred, average="macro", zero_division=0
        )
        classes, counts = np.unique(y, return_counts=True)
        return ModelMetrics(
            accuracy=float(accuracy_score(y, pred)),
            precision_macro=float(p),
            recall_macro=float(r),
            f1_macro=float(f1),
            confusion_matrix=confusion_matrix(y, pred).tolist(),
            n_train=int(getattr(self, "_n_train", 0)),
            n_test=int(len(y)),
            n_classes=int(len(classes)),
            n_features=int(X.shape[1]) if X.ndim > 1 else 1,
            train_time_s=round(self._train_time_s, 6),
            inference_time_s=round(infer_s, 6),
            inference_time_per_sample_ms=round(infer_s / max(1, len(y)) * 1000, 6),
            # Majority-class rate, not 1/n_classes -- the honest baseline for
            # imbalanced label sets.
            chance_accuracy=float(counts.max() / counts.sum()),
            extra={"hyperparams": self.hyperparams},
        )

    def save(self, path: str) -> str:
        with open(path, "wb") as fh:
            pickle.dump({"name": self.name, "hyperparams": self.hyperparams,
                         "state": self._state()}, fh)
        return path

    @classmethod
    def load(cls, path: str) -> Model:
        with open(path, "rb") as fh:
            blob = pickle.load(fh)
        model = cls(**blob["hyperparams"])
        model._restore(blob["state"])
        model._fitted = True
        return model

    def _state(self) -> Any:  # pragma: no cover - overridden where needed
        return self.__dict__

    def _restore(self, state: Any) -> None:  # pragma: no cover
        self.__dict__.update(state)

    def describe(self) -> dict:
        return {"name": self.name, "temporal": self.temporal,
                "hyperparams": self.hyperparams, "fitted": self._fitted}

    def _timed_fit(self, fn) -> Model:
        t0 = time.perf_counter()
        fn()
        self._train_time_s = time.perf_counter() - t0
        self._fitted = True
        return self


def metrics_to_json(metrics: ModelMetrics, path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(metrics.to_dict(), fh, indent=2)
    return path
