"""Shared fixtures for BioCompute tests.

Everything here is generated from the seeded simulator, so the whole default test
suite runs offline and deterministically. Only tests explicitly marked
`@pytest.mark.integration` touch the live FinalSpark service, and those are
excluded by the project's default `addopts = -m 'not integration'`.
"""

from __future__ import annotations

import numpy as np
import pytest

from biocompute.providers.simulator.adapter import SimulatorProvider


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
