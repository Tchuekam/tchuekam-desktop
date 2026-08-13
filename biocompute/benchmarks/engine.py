"""Benchmark engine: compare approaches on an identical task.

The comparison must be fair, so every model sees the same features, the same folds
and the same seed. Anything not measured is reported as None, never estimated.

The `cost_usd` and `energy_joules` columns exist so that an unmeasured cost is
VISIBLE as unmeasured. A benchmark table full of Nones in those columns is an
honest table -- it says we compared accuracy and speed but not economics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from biocompute.models.base import Model
from biocompute.models.evaluation import CVResult, cross_validate, permutation_test


@dataclass
class BenchmarkTask:
    """One task every approach is evaluated on."""

    name: str
    description: str
    X: np.ndarray
    y: np.ndarray
    n_splits: int = 5
    seed: int = 0
    #: Free-form notes about where the data came from (provider, biological or not).
    data_provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def chance(self) -> float:
        _, counts = np.unique(self.y, return_counts=True)
        return float(counts.max() / counts.sum())


@dataclass
class BenchmarkRow:
    """One approach's result on one task."""

    model: str
    accuracy_mean: float
    accuracy_std: float
    f1_mean: float
    chance: float
    above_chance_margin: float
    train_time_s: float
    inference_time_s: float
    n_train_samples: int
    p_value: float | None = None
    #: None means NOT MEASURED. It is never estimated or taken from a vendor claim.
    energy_joules: float | None = None
    cost_usd: float | None = None
    hardware: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)


class BenchmarkEngine:
    """Runs every registered approach on every task, under identical conditions."""

    def __init__(self, permutation_tests: bool = True, n_permutations: int = 200):
        self.permutation_tests = permutation_tests
        self.n_permutations = n_permutations
        self.rows: list[tuple[str, BenchmarkRow]] = []

    def run(
        self,
        task: BenchmarkTask,
        models: list[Callable[[], Model]],
        hardware: str | None = None,
    ) -> list[BenchmarkRow]:
        out: list[BenchmarkRow] = []
        for factory in models:
            cv: CVResult = cross_validate(
                factory, task.X, task.y, n_splits=task.n_splits, seed=task.seed
            )
            p = None
            if self.permutation_tests:
                p = permutation_test(
                    factory, task.X, task.y,
                    n_permutations=self.n_permutations,
                    n_splits=task.n_splits, seed=task.seed,
                )["p_value"]

            row = BenchmarkRow(
                model=cv.model_name,
                accuracy_mean=round(cv.accuracy_mean, 4),
                accuracy_std=round(cv.accuracy_std, 4),
                f1_mean=round(cv.f1_mean, 4),
                chance=round(cv.chance_accuracy, 4),
                above_chance_margin=round(cv.accuracy_mean - cv.chance_accuracy, 4),
                train_time_s=cv.train_time_s,
                inference_time_s=cv.inference_time_s,
                n_train_samples=cv.n_samples,
                p_value=p,
                energy_joules=None,  # not measured
                cost_usd=None,  # not measured
                hardware=hardware,
                notes=list(cv.notes),
            )
            out.append(row)
            self.rows.append((task.name, row))
        return out

    # ------------------------------------------------------------- rendering

    def to_dict(self) -> dict:
        by_task: dict[str, list[dict]] = {}
        for task_name, row in self.rows:
            by_task.setdefault(task_name, []).append(row.to_dict())
        return {
            "tasks": by_task,
            "measurement_policy": {
                "energy_joules": "None means NOT MEASURED. Never estimated.",
                "cost_usd": "None means NOT MEASURED. Never estimated.",
                "chance": "majority-class rate, not 1/n_classes",
                "significance": (
                    "permutation test with shuffled labels; p = (1 + #{null >= obs}) "
                    "/ (1 + n_permutations)"
                ),
            },
        }

    def render_table(self, task_name: str | None = None) -> str:
        rows = [(t, r) for t, r in self.rows if task_name is None or t == task_name]
        if not rows:
            return "(no benchmark rows)"

        hdr = (
            f"{'model':<24} {'acc':>7} {'+/-':>6} {'chance':>7} {'margin':>7} "
            f"{'p':>8} {'train_s':>8} {'infer_s':>8} {'energy':>7} {'cost':>6}"
        )
        lines = [hdr, "-" * len(hdr)]
        current = None
        for task, r in rows:
            if task != current:
                lines.insert(len(lines) - 0, f"\nTASK: {task}") if current else None
                current = task
            p = f"{r.p_value:.4f}" if r.p_value is not None else "n/a"
            lines.append(
                f"{r.model:<24} {r.accuracy_mean:>7.3f} {r.accuracy_std:>6.3f} "
                f"{r.chance:>7.3f} {r.above_chance_margin:>+7.3f} {p:>8} "
                f"{r.train_time_s:>8.3f} {r.inference_time_s:>8.4f} "
                f"{'n/m':>7} {'n/m':>6}"
            )
        lines += [
            "",
            "n/m = NOT MEASURED (never estimated).",
            "chance = majority-class rate. margin = accuracy - chance.",
        ]
        return "\n".join(lines)
