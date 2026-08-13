"""Statistically defensible evaluation.

Two rules this module enforces, because both are easy to get wrong and both would
invalidate any decoding claim:

1. **Chance is not 1/n_classes.** With imbalanced labels the majority-class rate is
   higher. `ModelMetrics.chance_accuracy` uses the majority rate.

2. **Beating chance on one split is not evidence.** With small n -- and biological
   datasets are always small n -- cross-validated accuracy above chance happens
   readily by luck. `permutation_test()` shuffles the labels many times and
   rebuilds the null distribution empirically. Report the p-value or do not claim
   a result.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from biocompute.models.base import Model, ModelMetrics


@dataclass
class CVResult:
    """Cross-validated performance."""

    model_name: str
    accuracy_mean: float
    accuracy_std: float
    accuracy_folds: list[float]
    f1_mean: float
    chance_accuracy: float
    n_splits: int
    n_samples: int
    n_features: int
    train_time_s: float
    inference_time_s: float
    permutation_p_value: float | None = None
    permutation_null_mean: float | None = None
    permutation_null_std: float | None = None
    n_permutations: int | None = None
    energy_joules: float | None = None
    cost_usd: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)

    @property
    def above_chance(self) -> bool:
        return self.accuracy_mean > self.chance_accuracy

    @property
    def significant(self, alpha: float = 0.05) -> bool:
        return self.permutation_p_value is not None and self.permutation_p_value < alpha


def cross_validate(
    model_factory: Callable[[], Model],
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5,
    seed: int = 0,
) -> CVResult:
    """Stratified k-fold cross-validation."""
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import StratifiedKFold

    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y)
    model_name = model_factory().name  # built once; do not re-instantiate per fold

    _, counts = np.unique(y, return_counts=True)
    min_class = int(counts.min())
    effective_splits = min(n_splits, min_class)
    notes: list[str] = []
    if effective_splits < n_splits:
        notes.append(
            f"n_splits reduced {n_splits} -> {effective_splits}: smallest class has "
            f"{min_class} samples"
        )
    if effective_splits < 2:
        raise ValueError(
            f"cannot cross-validate: smallest class has {min_class} sample(s)"
        )

    skf = StratifiedKFold(n_splits=effective_splits, shuffle=True, random_state=seed)
    accs, f1s = [], []
    total_train = total_infer = 0.0

    for tr, te in skf.split(X, y):
        m = model_factory()
        m.fit(X[tr], y[tr])
        total_train += m._train_time_s
        t0 = time.perf_counter()
        pred = m.predict(X[te])
        total_infer += time.perf_counter() - t0
        accs.append(float(accuracy_score(y[te], pred)))
        f1s.append(float(f1_score(y[te], pred, average="macro", zero_division=0)))

    if len(y) < 50:
        notes.append(
            f"n={len(y)} is small; cross-validated accuracy is high-variance. "
            f"Treat a permutation p-value as mandatory, not optional."
        )

    return CVResult(
        model_name=model_name,
        accuracy_mean=float(np.mean(accs)),
        accuracy_std=float(np.std(accs)),
        accuracy_folds=[round(a, 6) for a in accs],
        f1_mean=float(np.mean(f1s)),
        chance_accuracy=float(counts.max() / counts.sum()),
        n_splits=effective_splits,
        n_samples=int(len(y)),
        n_features=int(X.shape[1]),
        train_time_s=round(total_train, 6),
        inference_time_s=round(total_infer, 6),
        notes=notes,
    )


def permutation_test(
    model_factory: Callable[[], Model],
    X: np.ndarray,
    y: np.ndarray,
    n_permutations: int = 200,
    n_splits: int = 5,
    seed: int = 0,
    max_seconds: float | None = 300.0,
) -> dict[str, Any]:
    """Empirical null: shuffle labels, re-run CV, compare.

    p = (1 + #{null >= observed}) / (1 + n_permutations)

    The +1 in the numerator is deliberate -- it keeps p strictly positive, so a
    result can never be reported as p = 0.

    `max_seconds` bounds wall-clock cost. If the budget forces fewer permutations
    than requested, the reduction is RECORDED in the returned dict and in the
    result notes -- never silently applied, because a smaller permutation count
    raises the floor on the achievable p-value.
    """
    t0 = time.perf_counter()
    observed = cross_validate(model_factory, X, y, n_splits=n_splits, seed=seed)
    per_run_s = max(time.perf_counter() - t0, 1e-6)

    requested = n_permutations
    budget_note = None
    if max_seconds is not None:
        affordable = max(1, int(max_seconds / per_run_s))
        if affordable < n_permutations:
            n_permutations = affordable
            budget_note = (
                f"n_permutations reduced {requested} -> {n_permutations} to stay within "
                f"a {max_seconds:.0f}s budget ({per_run_s:.2f}s per CV run). "
                f"Minimum achievable p-value is {1 / (1 + n_permutations):.4f}."
            )
            observed.notes.append(budget_note)

    rng = np.random.default_rng(seed)
    null = []
    for i in range(n_permutations):
        y_perm = rng.permutation(y)
        try:
            null.append(
                cross_validate(model_factory, X, y_perm, n_splits=n_splits, seed=seed + i).accuracy_mean
            )
        except ValueError:  # pragma: no cover - degenerate shuffle
            continue

    null_arr = np.array(null)
    p = float((1 + np.sum(null_arr >= observed.accuracy_mean)) / (1 + len(null_arr)))

    observed.permutation_p_value = p
    observed.permutation_null_mean = float(null_arr.mean())
    observed.permutation_null_std = float(null_arr.std())
    observed.n_permutations = len(null_arr)

    return {
        "result": observed,
        "observed_accuracy": observed.accuracy_mean,
        "null_mean": observed.permutation_null_mean,
        "null_std": observed.permutation_null_std,
        "p_value": p,
        "n_permutations": len(null_arr),
        "n_permutations_requested": requested,
        "min_achievable_p": round(1 / (1 + len(null_arr)), 6),
        "budget_note": budget_note,
        "seconds_per_cv_run": round(per_run_s, 4),
        "significant_at_0.05": p < 0.05,
        "interpretation": _interpret(observed.accuracy_mean, observed.permutation_null_mean, p),
    }


def permutation_test_best_of(
    model_factories: list[Callable[[], Model]],
    X: np.ndarray,
    y: np.ndarray,
    n_permutations: int = 100,
    n_splits: int = 5,
    seed: int = 0,
    max_seconds: float | None = 300.0,
) -> dict[str, Any]:
    """Permutation test for the BEST of several models -- the correct null when
    you try K models and report the winner.

    WHY THIS EXISTS
    ---------------
    Testing the winner of K models against a null built for ONE model is a
    winner's-curse error: the maximum of K noisy estimates is biased upward, so
    the single-model null is too lenient and noise gets reported as signal.

    Measured on this codebase with 5 models on genuinely label-free synthetic data:
    each individual model averaged ~0.49 accuracy (unbiased), but the best-of-5
    averaged 0.537 -- a systematic +0.04 inflation from selection alone.

    The fix is to apply the SAME selection procedure inside every permutation:
    shuffle the labels, evaluate all K models, take the max. The resulting null is
    the distribution of "best of K under no signal", which is what the observed
    statistic must be compared against.
    """
    t0 = time.perf_counter()
    observed_cvs = [
        cross_validate(f, X, y, n_splits=n_splits, seed=seed) for f in model_factories
    ]
    per_round_s = max(time.perf_counter() - t0, 1e-6)

    best = max(observed_cvs, key=lambda c: c.accuracy_mean)

    requested = n_permutations
    budget_note = None
    if max_seconds is not None:
        affordable = max(1, int(max_seconds / per_round_s))
        if affordable < n_permutations:
            n_permutations = affordable
            budget_note = (
                f"n_permutations reduced {requested} -> {n_permutations} to stay within "
                f"a {max_seconds:.0f}s budget ({per_round_s:.2f}s per round of "
                f"{len(model_factories)} models). Minimum achievable p-value is "
                f"{1 / (1 + n_permutations):.4f}."
            )
            best.notes.append(budget_note)

    rng = np.random.default_rng(seed)
    null = []
    for i in range(n_permutations):
        y_perm = rng.permutation(y)
        try:
            null.append(
                max(
                    cross_validate(f, X, y_perm, n_splits=n_splits, seed=seed + i).accuracy_mean
                    for f in model_factories
                )
            )
        except ValueError:  # pragma: no cover - degenerate shuffle
            continue

    null_arr = np.array(null)
    p = float((1 + np.sum(null_arr >= best.accuracy_mean)) / (1 + len(null_arr)))

    best.permutation_p_value = p
    best.permutation_null_mean = float(null_arr.mean())
    best.permutation_null_std = float(null_arr.std())
    best.n_permutations = len(null_arr)
    best.notes.append(
        f"p-value accounts for model selection across {len(model_factories)} candidates "
        f"(best-of-K permutation null)"
    )

    return {
        "result": best,
        "best_model": best.model_name,
        "observed_accuracy": best.accuracy_mean,
        "all_model_accuracies": {c.model_name: c.accuracy_mean for c in observed_cvs},
        "null_mean": best.permutation_null_mean,
        "null_std": best.permutation_null_std,
        "p_value": p,
        "n_permutations": len(null_arr),
        "n_permutations_requested": requested,
        "n_models_considered": len(model_factories),
        "min_achievable_p": round(1 / (1 + len(null_arr)), 6),
        "budget_note": budget_note,
        "seconds_per_round": round(per_round_s, 4),
        "selection_corrected": True,
        "significant_at_0.05": p < 0.05,
        "interpretation": _interpret(best.accuracy_mean, best.permutation_null_mean, p),
    }


def _interpret(observed: float, null_mean: float, p: float) -> str:
    if p >= 0.05:
        return (
            f"NOT SIGNIFICANT (p={p:.4f}). Observed accuracy {observed:.3f} is not "
            f"distinguishable from the shuffled-label null ({null_mean:.3f}). "
            f"No decoding claim is supported."
        )
    return (
        f"Significant at alpha=0.05 (p={p:.4f}). Observed {observed:.3f} vs null "
        f"{null_mean:.3f}. This shows the labels are decodable from these features; "
        f"it does NOT by itself identify WHICH property carries the information -- "
        f"run the stated controls before attributing it to a mechanism."
    )


def attach_permutation(metrics: ModelMetrics, perm: dict[str, Any]) -> ModelMetrics:
    metrics.permutation_p_value = perm["p_value"]
    metrics.permutation_null_mean = perm["null_mean"]
    return metrics
