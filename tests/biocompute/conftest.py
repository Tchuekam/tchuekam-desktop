"""Shared fixtures for BioCompute tests.

Everything here is generated from the seeded simulator, so the whole default test
suite runs offline and deterministically. Only tests explicitly marked
`@pytest.mark.integration` touch the live FinalSpark service, and those are
excluded by the project's default `addopts = -m 'not integration'`.

These tests need the scientific stack from the optional `biocompute` extra
(numpy, scipy, scikit-learn). CI installs it explicitly — see
.github/workflows/tests.yml — so they really run there. On a checkout
installed with only `.[all,dev]` the directory is skipped instead of failing
collection with ImportError.
"""

from __future__ import annotations

import importlib.util

import pytest

# Only consulted when pytest collects the directory, which is how a human
# invokes it. `scripts/run_tests_parallel.py` names each file explicitly, and
# pytest does not consult `collect_ignore*` for explicitly-named paths — that
# path relies on CI having installed the extra.
if importlib.util.find_spec("numpy") is None:  # pragma: no cover - env-dependent
    collect_ignore_glob = ["test_*.py"]

import numpy as np  # noqa: E402

from biocompute.providers.simulator.adapter import SimulatorProvider  # noqa: E402


@pytest.fixture
def sim() -> SimulatorProvider:
    return SimulatorProvider(n_channels=6, seed=42, samples_per_segment=800)


@pytest.fixture
def recording(sim):
    from biocompute.core.schema import RecordRequest

    return sim.record(RecordRequest(n_segments=3, experiment_id="test"))


@pytest.fixture
def labeled_recording(sim):
    return sim.record_labeled(n_classes=2, trials_per_class=12, seed=7)


@pytest.fixture
def null_recording(sim):
    """Same generator with the stimulus effect switched off — classes are identical."""
    return sim.record_labeled(n_classes=2, trials_per_class=12, seed=7, response_gain=0.0)


@pytest.fixture
def processed(recording):
    from biocompute.neural.pipeline import default_pipeline

    return default_pipeline().run(recording), recording


@pytest.fixture
def spiky_signal():
    """Flat noise with three large spikes at known positions on one channel."""
    rng = np.random.default_rng(0)
    fs, n = 3750.0, 2000
    sig = rng.normal(0, 5.0, size=(1, 1, n)).astype(np.float32)
    positions = [300, 900, 1500]
    for p in positions:
        sig[0, 0, p] = -120.0
    return sig, positions, fs
