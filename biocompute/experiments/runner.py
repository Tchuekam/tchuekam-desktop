"""Experiment runner: spec + recording -> decoded result + manifest.

Enforces the rules that keep results honest:
  - labels must come from a validated LabelSource (no manufactured labels)
  - every decoding claim gets a permutation test
  - the conclusion is emitted as evidence-levelled Statements, and a
    non-significant result produces a plainly-stated negative finding rather
    than a hedge
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np

from biocompute.core.provenance import ExperimentManifest
from biocompute.core.schema import Recording
from biocompute.experiments.spec import (
    EvidenceLevel,
    ExperimentResult,
    ExperimentSpec,
    Statement,
)
from biocompute.models.base import Model
from biocompute.models.evaluation import cross_validate, permutation_test_best_of
from biocompute.neural.analysis import summarize
from biocompute.neural.pipeline import Pipeline, default_pipeline


class ExperimentRunner:
    """Runs a pre-registered ExperimentSpec against a Recording."""

    def __init__(self, output_dir: str | Path = "biocompute_runs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        spec: ExperimentSpec,
        recording: Recording,
        labels: np.ndarray | list[int] | None,
        models: list[Callable[[], Model]],
        pipeline: Pipeline | None = None,
        n_permutations: int = 200,
        n_splits: int = 5,
        provider_config: dict[str, Any] | None = None,
    ) -> ExperimentResult:
        # 1. Labels must be legitimate. Refuse to proceed otherwise.
        spec.label_source.validate()

        pipeline = pipeline or default_pipeline()
        ctx = pipeline.run(recording)
        analysis = summarize(ctx, recording)

        manifest = ExperimentManifest.create(
            name=spec.name,
            provider=recording.provider,
            provider_config=provider_config or {},
            dataset_hash=recording.data_hash(),
            dataset_reference=recording.raw_data_reference,
            random_seeds=dict(spec.seeds),
            processing_parameters=[
                {"name": s.name, "params": s.params} for s in recording.processing_parameters
            ],
            data_source_is_biological=bool(
                (recording.provider_metadata or {}).get("biological", False)
            ),
            notes=[f"pipeline: {' -> '.join(pipeline.describe())}"],
        )

        result = ExperimentResult(
            spec=spec,
            manifest_path=None,
            recording_summary=analysis,
            limitations=list(spec.limitations),
        )

        # 2. Descriptive-only experiment (no labels) stops here, honestly.
        if labels is None:
            result.conclusion = [
                Statement(
                    "Recording captured and characterised; no labels were available, "
                    "so no decoding claim is made.",
                    EvidenceLevel.MEASUREMENT,
                    f"{analysis['population']['total_events']} events across "
                    f"{analysis['population']['n_channels']} channels",
                )
            ]
            result.next_experiment = (
                "Obtain a condition the setup genuinely controls or knows, so that "
                "labels are valid, then repeat as a decoding experiment."
            )
            manifest.metrics = {"analysis_only": True}
            result.manifest_path = manifest.save(
                self.output_dir / f"{manifest.experiment_id}.manifest.json"
            )
            return result

        # 3. Decode.
        X = ctx.features
        y = np.asarray(labels)
        if X is None:
            raise RuntimeError("pipeline produced no features; include ExtractFeatures")
        if len(y) != len(X):
            raise ValueError(
                f"{len(y)} labels for {len(X)} feature rows -- one label per segment"
            )

        for factory in models:
            cv = cross_validate(factory, X, y, n_splits=n_splits,
                                seed=spec.seeds.get("global", 0))
            result.model_results[cv.model_name] = cv.to_dict()

        # 4. Permutation-test with SELECTION CORRECTION.
        #    We report the best of K models, so the null must also be "best of K".
        #    Testing the winner against a single-model null is a winner's-curse
        #    error that inflates Type I error (measured here at ~+0.04 accuracy).
        perm = permutation_test_best_of(
            models, X, y,
            n_permutations=n_permutations, n_splits=n_splits,
            seed=spec.seeds.get("global", 0),
        )
        best_name = perm["best_model"]
        result.model_results[best_name] = perm["result"].to_dict()
        result.primary_metric = perm["observed_accuracy"]
        result.chance_level = perm["result"].chance_accuracy
        result.p_value = perm["p_value"]

        result.conclusion = self._conclude(spec, result, perm, best_name, analysis)

        manifest.model_versions = {
            f().name: f().describe() for f in models
        }
        manifest.metrics = {
            "best_model": best_name,
            "accuracy_mean": result.primary_metric,
            "chance_accuracy": result.chance_level,
            "p_value": result.p_value,
            "p_value_selection_corrected": perm.get("selection_corrected", False),
            "n_models_considered": perm.get("n_models_considered"),
            "n_permutations": perm["n_permutations"],
            "min_achievable_p": perm.get("min_achievable_p"),
            "budget_note": perm.get("budget_note"),
            "all_models": {k: v["accuracy_mean"] for k, v in result.model_results.items()},
        }
        result.manifest_path = manifest.save(
            self.output_dir / f"{manifest.experiment_id}.manifest.json"
        )
        return result

    # ---------------------------------------------------------------- verdict

    def _conclude(self, spec, result, perm, best_name, analysis) -> list[Statement]:
        out: list[Statement] = [
            Statement(
                f"Pipeline captured and processed {analysis['recording']['n_segments']} "
                f"segments ({analysis['recording']['duration_s']:.2f} s of signal) from "
                f"provider '{analysis['recording']['provider']}'.",
                EvidenceLevel.MEASUREMENT,
                f"data hash {analysis['recording']['data_hash']}",
            ),
            Statement(
                f"Best model '{best_name}' reached {result.primary_metric:.3f} "
                f"cross-validated accuracy against a chance level of "
                f"{result.chance_level:.3f}.",
                EvidenceLevel.MEASUREMENT,
                f"{perm['result'].n_splits}-fold stratified CV, n={perm['result'].n_samples}",
            ),
        ]

        if result.hypothesis_supported:
            out.append(
                Statement(
                    f"The labels are decodable from these features "
                    f"(p={result.p_value:.4f} < {spec.alpha}). Evidence FOR: "
                    f"{spec.evidence_for}",
                    EvidenceLevel.MEASUREMENT,
                    f"permutation test, {perm['n_permutations']} shuffles, "
                    f"null mean {perm['null_mean']:.3f}",
                )
            )
            if spec.known_confounds:
                out.append(
                    Statement(
                        "Decodability alone does not identify the mechanism. These "
                        f"confounds remain open and must be excluded before any "
                        f"mechanistic claim: {'; '.join(spec.known_confounds)}",
                        EvidenceLevel.INFERENCE,
                        "stated in the pre-registered spec",
                    )
                )
        else:
            out.append(
                Statement(
                    f"NEGATIVE RESULT. Accuracy is not distinguishable from the "
                    f"shuffled-label null (p={result.p_value:.4f}). Evidence AGAINST: "
                    f"{spec.evidence_against}. The null hypothesis is not rejected.",
                    EvidenceLevel.MEASUREMENT,
                    f"permutation test, {perm['n_permutations']} shuffles, "
                    f"null mean {perm['null_mean']:.3f}",
                )
            )

        out.append(
            Statement(
                "This experiment says nothing about whether biological substrate "
                "outperforms conventional computing. That requires a matched-task "
                "benchmark with measured cost and energy.",
                EvidenceLevel.FACT,
                "scope of the experiment as specified",
            )
        )
        return out
