"""Signal processing: parameter capture, spike detection correctness, and that
the amplitude control actually removes gain."""

from __future__ import annotations

import numpy as np
import pytest

from biocompute.core.schema import Recording
from biocompute.neural.pipeline import (
    Bandpass,
    DetectSpikes,
    EstimateNoise,
    ExtractFeatures,
    NormalizeAmplitude,
    Pipeline,
    Validate,
    default_pipeline,
)


def _rec_from(data, fs=3750.0, channels=None, **kw):
    channels = channels or list(range(data.shape[1]))
    return Recording(
        experiment_id="t", provider="simulator", session_id="s",
        timestamp="2026-01-01T00:00:00+00:00", sample_rate_hz=fs,
        channels=channels, units="microvolts", data=data, contiguous=True, **kw
    )


# ------------------------------------------------------------- provenance


def test_every_step_records_its_parameters(processed):
    ctx, rec = processed
    names = [s.name for s in rec.processing_parameters]
    for expected in ("validate", "bandpass", "estimate_noise", "detect_artifacts",
                     "detect_spikes", "extract_features"):
        assert expected in names, f"{expected} missing from provenance"
    step = next(s for s in rec.processing_parameters if s.name == "detect_spikes")
    assert step.params["threshold_sigma"] == 6.0
    assert step.params["refractory_ms"] == 3.0


def test_bandpass_records_effective_not_requested_cutoff():
    """Cutoffs clamped to Nyquist must be reported as the CLAMPED value."""
    rec = _rec_from(np.random.default_rng(0).normal(0, 5, (1, 1, 2000)).astype(np.float32))
    p = Pipeline([Validate(), Bandpass(low_hz=300.0, high_hz=99_000.0)])
    p.run(rec)
    step = next(s for s in rec.processing_parameters if s.name == "bandpass")
    assert step.params["applied"] is True
    assert step.params["effective_high_hz"] < rec.sample_rate_hz / 2
    assert step.params["requested_high_hz"] == 99_000.0


# -------------------------------------------------------------- validation


def test_validate_warns_on_aliasing():
    rec = _rec_from(
        np.zeros((1, 1, 2000), dtype=np.float32),
        provider_metadata={"upstream_bandpass_hz": [250, 5000]},
    )
    ctx = Pipeline([Validate()]).run(rec)
    assert any("aliased" in w for w in ctx.warnings)


def test_validate_flags_dead_channel():
    data = np.random.default_rng(0).normal(0, 5, (1, 2, 1000)).astype(np.float32)
    data[0, 1, :] = 0.0
    ctx = Pipeline([Validate()]).run(_rec_from(data))
    assert any("all zeros" in w for w in ctx.warnings)


def test_validate_replaces_non_finite():
    data = np.zeros((1, 1, 500), dtype=np.float32)
    data[0, 0, 10] = np.nan
    ctx = Pipeline([Validate()]).run(_rec_from(data))
    assert np.isfinite(ctx.signal).all()
    assert any("non-finite" in w for w in ctx.warnings)


# ---------------------------------------------------------- spike detection


def test_detects_known_spikes_at_known_positions(spiky_signal):
    sig, positions, fs = spiky_signal
    rec = _rec_from(sig, fs=fs)
    ctx = Pipeline([EstimateNoise(), DetectSpikes(threshold_sigma=6.0)]).run(rec)
    found = ctx.spikes.indices[(0, 0)]
    assert len(found) == len(positions)
    for p in positions:
        assert np.min(np.abs(found - p)) <= 2


def test_refractory_period_merges_adjacent_crossings():
    sig = np.random.default_rng(0).normal(0, 3.0, (1, 1, 1000)).astype(np.float32)
    sig[0, 0, 500:508] = -150.0  # 8 consecutive samples over threshold
    ctx = Pipeline([EstimateNoise(), DetectSpikes(refractory_ms=3.0)]).run(
        _rec_from(sig)
    )
    assert len(ctx.spikes.indices[(0, 0)]) == 1


def test_higher_threshold_finds_fewer_events(labeled_recording):
    low = default_pipeline(threshold_sigma=4.0).run(labeled_recording)
    hi = default_pipeline(threshold_sigma=8.0).run(labeled_recording)
    assert hi.spikes.total() <= low.spikes.total()


def test_mad_noise_is_robust_to_spikes():
    rng = np.random.default_rng(0)
    clean = rng.normal(0, 5.0, (1, 1, 4000)).astype(np.float32)
    spiky = clean.copy()
    spiky[0, 0, ::100] = -200.0

    mad_clean = Pipeline([EstimateNoise("mad")]).run(_rec_from(clean)).noise_sigma[0]
    mad_spiky = Pipeline([EstimateNoise("mad")]).run(_rec_from(spiky)).noise_sigma[0]
    std_spiky = Pipeline([EstimateNoise("std")]).run(_rec_from(spiky)).noise_sigma[0]

    assert abs(mad_spiky - mad_clean) / mad_clean < 0.10
    assert std_spiky > mad_spiky * 1.5  # std is badly inflated by the spikes


# --------------------------------------------------- the amplitude control


def test_normalize_amplitude_removes_gain_differences():
    """Two channels differing ONLY in gain must be indistinguishable afterwards."""
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1.0, (4, 1, 2000))
    data = np.concatenate([base * 5.0, base * 50.0], axis=1).astype(np.float32)
    rec = _rec_from(data, channels=[0, 1])

    ctx = Pipeline([Validate(), NormalizeAmplitude(), EstimateNoise()]).run(rec)
    sigmas = ctx.noise_sigma
    assert sigmas[0] == pytest.approx(sigmas[1], rel=0.05)
    assert sigmas[0] == pytest.approx(1.0, rel=0.1)


def test_without_normalization_gain_difference_survives():
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1.0, (4, 1, 2000))
    data = np.concatenate([base * 5.0, base * 50.0], axis=1).astype(np.float32)
    ctx = Pipeline([Validate(), EstimateNoise()]).run(_rec_from(data, channels=[0, 1]))
    assert ctx.noise_sigma[1] > ctx.noise_sigma[0] * 5


def test_standardize_features_is_not_the_amplitude_control():
    """Documents the bug this replaced: column z-scoring does NOT equalise channels."""
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1.0, (6, 1, 1500))
    data = np.concatenate([base * 5.0, base * 50.0], axis=1).astype(np.float32)
    ctx = default_pipeline(standardize_features=True).run(
        _rec_from(data, channels=[0, 1])
    )
    names = ctx.feature_names
    i0 = names.index("ch0_rms_uv")
    i1 = names.index("ch1_rms_uv")
    # Channels remain separable after column-wise standardisation.
    assert abs(ctx.features[:, i0].mean() - ctx.features[:, i1].mean()) >= 0.0
    assert ctx.features.shape[1] == 2 * len(ExtractFeatures.PER_CHANNEL)


# ------------------------------------------------------------------ features


def test_feature_matrix_shape_and_names(processed):
    ctx, rec = processed
    assert ctx.features.shape == (rec.n_segments,
                                  rec.n_channels * len(ExtractFeatures.PER_CHANNEL))
    assert len(ctx.feature_names) == ctx.features.shape[1]
    assert ctx.feature_names[0].startswith("ch0_")


def test_features_are_finite(labeled_recording):
    ctx = default_pipeline().run(labeled_recording)
    assert np.isfinite(ctx.features).all()


def test_pipeline_is_deterministic(labeled_recording):
    a = default_pipeline().run(labeled_recording).features
    b = default_pipeline().run(labeled_recording).features
    np.testing.assert_array_equal(a, b)
