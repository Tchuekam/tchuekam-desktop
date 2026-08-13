"""Decoding, statistics, benchmarking, provenance, and the two properties that
keep results honest: no manufactured labels, and no winner's-curse p-values."""

from __future__ import annotations

import numpy as np
import pytest

from biocompute.benchmarks.engine import BenchmarkEngine, BenchmarkTask
from biocompute.core.provenance import ExperimentManifest
from biocompute.experiments.library import (
    channel_identity_dataset,
    e1_simulator_stimulus_decoding,
    e2_channel_identity_decoding,
)
from biocompute.experiments.runner import ExperimentRunner
from biocompute.experiments.spec import EvidenceLevel, LabelSource
from biocompute.models.baselines import (
    LogisticRegressionModel,
    MajorityClassModel,
    RandomForestModel,
)
from biocompute.models.evaluation import (
    cross_validate,
    permutation_test,
    permutation_test_best_of,
)
from biocompute.models.reservoir import (
    BiologicalReservoirStub,
    DigitalReservoir,
    ReservoirModel,
)
from biocompute.neural.analysis import channel_statistics, detect_bursts, summarize
from biocompute.neural.pipeline import default_pipeline

FAST = [MajorityClassModel, LogisticRegressionModel]


@pytest.fixture
def decodable(labeled_recording):
    ctx = default_pipeline().run(labeled_recording)
    return ctx.features, np.array(labeled_recording.stimulus_metadata["labels"])


@pytest.fixture
def undecodable(null_recording):
    ctx = default_pipeline().run(null_recording)
    return ctx.features, np.array(null_recording.stimulus_metadata["labels"])


# --------------------------------------------------------------------- models


def test_models_fit_predict_and_report_metrics(decodable):
    X, y = decodable
    m = LogisticRegressionModel().fit(X, y)
    metrics = m.evaluate(X, y)
    assert 0.0 <= metrics.accuracy <= 1.0
    assert metrics.n_classes == 2
    assert metrics.train_time_s > 0
    assert len(metrics.confusion_matrix) == 2


def test_energy_and_cost_are_none_not_invented(decodable):
    X, y = decodable
    metrics = LogisticRegressionModel().fit(X, y).evaluate(X, y)
    assert metrics.energy_joules is None
    assert metrics.cost_usd is None


def test_chance_uses_majority_class_not_one_over_k():
    X = np.random.default_rng(0).normal(size=(30, 4))
    y = np.array([0] * 24 + [1] * 6)  # imbalanced
    metrics = MajorityClassModel().fit(X, y).evaluate(X, y)
    assert metrics.chance_accuracy == pytest.approx(0.8)


def test_predict_before_fit_raises():
    with pytest.raises(RuntimeError):
        LogisticRegressionModel().predict(np.zeros((2, 3)))


def test_model_save_load_roundtrip(decodable, tmp_path):
    X, y = decodable
    m = LogisticRegressionModel().fit(X, y)
    path = tmp_path / "m.pkl"
    m.save(str(path))
    back = LogisticRegressionModel.load(str(path))
    np.testing.assert_array_equal(m.predict(X), back.predict(X))


# ------------------------------------------------------------------ reservoir


def test_digital_reservoir_respects_spectral_radius():
    r = DigitalReservoir(n_units=40, spectral_radius=0.8, seed=0)
    assert np.max(np.abs(np.linalg.eigvals(r.W))) == pytest.approx(0.8, rel=1e-6)


def test_reservoir_state_evolves_and_resets():
    r = DigitalReservoir(n_units=20, seed=0)
    r.reset()
    s1 = r.step(np.ones(20))
    s2 = r.step(np.ones(20))
    assert not np.allclose(s1, s2)
    r.reset()
    assert np.allclose(r._state, 0)


def test_reservoir_model_trains_only_the_readout(decodable):
    X, y = decodable
    m = ReservoirModel(n_units=60, seed=0).fit(X, y)
    d = m.describe()
    assert "readout only" in d["trained_components"][0]
    assert d["backend"]["biological"] is False


def test_biological_reservoir_is_not_implemented():
    stub = BiologicalReservoirStub()
    with pytest.raises(NotImplementedError, match="does not implement"):
        stub.step(np.zeros(4))
    with pytest.raises(NotImplementedError):
        stub.reset()


# ----------------------------------------------------------------- evaluation


def test_cross_validate_finds_real_signal(decodable):
    X, y = decodable
    cv = cross_validate(LogisticRegressionModel, X, y, n_splits=4)
    assert cv.accuracy_mean > cv.chance_accuracy


def test_cross_validate_reduces_splits_for_tiny_classes():
    X = np.random.default_rng(0).normal(size=(10, 3))
    y = np.array([0] * 8 + [1] * 2)
    cv = cross_validate(MajorityClassModel, X, y, n_splits=5)
    assert cv.n_splits == 2
    assert any("n_splits reduced" in n for n in cv.notes)


def test_permutation_p_value_is_never_zero(decodable):
    X, y = decodable
    perm = permutation_test(LogisticRegressionModel, X, y, n_permutations=20, n_splits=3)
    assert perm["p_value"] > 0
    assert perm["p_value"] >= perm["min_achievable_p"]


def test_permutation_budget_reduction_is_reported(decodable):
    """A reduced permutation count must be surfaced, never silently applied."""
    X, y = decodable
    perm = permutation_test(
        RandomForestModel, X, y, n_permutations=10_000, n_splits=3, max_seconds=1.0
    )
    assert perm["n_permutations"] < perm["n_permutations_requested"]
    assert perm["budget_note"] is not None
    assert "reduced" in perm["budget_note"]


def test_null_data_is_not_significant(undecodable):
    """The pipeline must not manufacture signal that is not there."""
    X, y = undecodable
    perm = permutation_test_best_of(
        FAST, X, y, n_permutations=60, n_splits=3, max_seconds=15.0
    )
    assert perm["p_value"] > 0.05, f"false positive on null data: p={perm['p_value']}"


def test_best_of_k_null_is_stricter_than_single_model_null(undecodable):
    """Selection correction must RAISE the null mean; that is the winner's-curse fix.

    Uses only fast models so this stays inside the repo's 30s per-test cap.
    """
    X, y = undecodable
    from biocompute.models.baselines import SVMModel

    single = permutation_test(
        LogisticRegressionModel, X, y, n_permutations=30, n_splits=3, max_seconds=8.0
    )
    best_of = permutation_test_best_of(
        [LogisticRegressionModel, SVMModel, MajorityClassModel],
        X, y, n_permutations=30, n_splits=3, max_seconds=8.0,
    )
    assert best_of["null_mean"] >= single["null_mean"]
    assert best_of["selection_corrected"] is True
    assert best_of["n_models_considered"] == 3


# ------------------------------------------------------------------- analysis


def test_burst_detection_groups_by_max_isi():
    times = np.array([0.0, 0.01, 0.02, 5.0, 5.01, 5.02, 5.03])
    bursts = detect_bursts(times, max_isi_s=0.1, min_events=3)
    assert len(bursts) == 2
    assert bursts[0][2] == 3 and bursts[1][2] == 4


def test_burst_detection_needs_minimum_events():
    assert detect_bursts(np.array([0.0, 0.01]), min_events=3) == []


def test_channel_statistics_cover_every_channel(processed):
    ctx, rec = processed
    stats = channel_statistics(ctx)
    assert set(stats) == {str(c) for c in rec.channels}
    for s in stats.values():
        assert s["event_count"] >= 0
        assert s["noise_sigma_uv"] > 0


def test_summarize_includes_provenance_and_caveats(processed):
    ctx, rec = processed
    out = summarize(ctx, rec)
    assert out["recording"]["data_hash"]
    assert any("NOT sorted spikes" in n for n in out["interpretation_notes"])


def test_population_stats_handle_single_channel(labeled_recording):
    """Channel-identity reshape yields 1-channel samples; must not crash."""
    rec, labels = channel_identity_dataset(labeled_recording)
    ctx = default_pipeline().run(rec)
    out = summarize(ctx, rec)
    assert out["population"]["signal_correlation_mean"] is None
    assert out["population"]["n_channels"] == 1


# ------------------------------------------------------------------ benchmark


def test_benchmark_reports_unmeasured_as_none(decodable):
    X, y = decodable
    task = BenchmarkTask(name="t", description="d", X=X, y=y, n_splits=3)
    rows = BenchmarkEngine(permutation_tests=False).run(task, FAST)
    assert len(rows) == 2
    for r in rows:
        assert r.energy_joules is None
        assert r.cost_usd is None
    assert "NOT MEASURED" in BenchmarkEngine().to_dict()["measurement_policy"]["energy_joules"]


def test_benchmark_table_renders(decodable):
    X, y = decodable
    engine = BenchmarkEngine(permutation_tests=False)
    engine.run(BenchmarkTask(name="t", description="d", X=X, y=y, n_splits=3), FAST)
    table = engine.render_table()
    assert "n/m" in table and "majority_class" in table


# ----------------------------------------------------------------- provenance


def test_manifest_captures_environment_and_fingerprint(tmp_path):
    m = ExperimentManifest.create("test-exp", provider="simulator",
                                  random_seeds={"global": 1}, dataset_hash="abc")
    assert m.experiment_id.startswith("test-exp-")
    assert m.environment["python"]
    fp = m.fingerprint()
    path = m.save(tmp_path / "m.json")
    back = ExperimentManifest.load(path)
    assert back.fingerprint() == fp


def test_manifest_fingerprint_changes_with_seed(tmp_path):
    a = ExperimentManifest.create("e", random_seeds={"global": 1})
    b = ExperimentManifest.create("e", random_seeds={"global": 2})
    assert a.fingerprint() != b.fingerprint()


# ----------------------------------------------------------------- experiments


def test_invalid_label_source_is_rejected():
    """Manufactured labels must be refused, not silently used."""
    bad = LabelSource(
        description="assumed stimulus from timing", is_ground_truth=False,
        valid_for_supervised_learning=False, caveats=["invented from an assumption"],
    )
    with pytest.raises(ValueError, match="Do not manufacture labels"):
        bad.validate()


def test_e1_spec_declares_falsification_criteria():
    spec = e1_simulator_stimulus_decoding()
    assert spec.evidence_for and spec.evidence_against
    assert spec.label_source.valid_for_supervised_learning
    assert any("null dataset" in c for c in spec.controls)


def test_e2_spec_names_the_gain_confound_and_its_control():
    spec = e2_channel_identity_decoding()
    assert any("amplitude" in c.lower() for c in spec.controls)
    assert any("noise amplitude" in c for c in spec.known_confounds)
    assert "NOT a stimulus label" in " ".join(spec.label_source.caveats)


def test_channel_identity_dataset_shapes_and_labels(labeled_recording):
    rec, labels = channel_identity_dataset(labeled_recording)
    n_seg, n_ch = labeled_recording.n_segments, labeled_recording.n_channels
    assert rec.data.shape == (n_seg * n_ch, 1, labeled_recording.n_samples)
    assert len(labels) == n_seg * n_ch
    assert set(labels) == set(labeled_recording.channels)
    assert "NOT a stimulus label" in rec.stimulus_metadata["note"]


def test_runner_end_to_end_produces_manifest_and_statements(labeled_recording, tmp_path):
    spec = e1_simulator_stimulus_decoding()
    labels = np.array(labeled_recording.stimulus_metadata["labels"])
    result = ExperimentRunner(output_dir=tmp_path).run(
        spec, labeled_recording, labels, FAST, n_permutations=20, n_splits=3
    )
    assert result.manifest_path
    assert result.conclusion
    levels = {s.level for s in result.conclusion}
    assert EvidenceLevel.MEASUREMENT in levels
    assert result.p_value is not None


def test_runner_without_labels_makes_no_decoding_claim(recording, tmp_path):
    spec = e1_simulator_stimulus_decoding()
    result = ExperimentRunner(output_dir=tmp_path).run(spec, recording, None, FAST)
    assert result.primary_metric is None
    assert result.hypothesis_supported is None
    assert any("no decoding claim" in s.text for s in result.conclusion)


def test_report_generation(labeled_recording, tmp_path):
    from biocompute.reporting.report import save_report

    spec = e1_simulator_stimulus_decoding()
    labels = np.array(labeled_recording.stimulus_metadata["labels"])
    result = ExperimentRunner(output_dir=tmp_path).run(
        spec, labeled_recording, labels, FAST, n_permutations=20, n_splits=3
    )
    paths = save_report(result, tmp_path)
    md = open(paths["markdown"], encoding="utf-8").read()
    assert "## Verdict:" in md
    assert "Reproducibility" in md
    assert "[MEASUREMENT]" in md
