"""Unit tests for BioCompute core interfaces, schema, registry, and capabilities."""

import pytest
import numpy as np
from biocompute.core.capabilities import Capability, ProviderCapabilities
from biocompute.core.registry import available, get_provider
from biocompute.core.schema import Recording, RecordRequest, ChannelLayout, ElectrodePosition, ProcessingStep
from biocompute.providers.simulator.adapter import SimulatorProvider
from biocompute.providers.finalspark.adapter import FinalSparkProvider


def test_provider_registry():
    provs = available()
    assert "simulator" in provs
    assert "finalspark" in provs


def test_capabilities_guard():
    caps = ProviderCapabilities.of(Capability.RECORDING)
    assert caps.supports(Capability.RECORDING)
    assert not caps.supports(Capability.STIMULATION)

    with pytest.raises(PermissionError):
        sim = SimulatorProvider()
        sim.stimulate()


def test_recording_schema_and_hash():
    data = np.random.normal(0, 10, size=(2, 4, 1600)).astype(np.float32)
    rec = Recording(
        experiment_id="test_exp",
        provider="simulator",
        session_id="test_sess",
        timestamp="2026-08-13T12:00:00Z",
        sample_rate_hz=3750.0,
        channels=[0, 1, 2, 3],
        units="microvolts",
        data=data,
        contiguous=True,
    )
    assert rec.n_segments == 2
    assert rec.n_channels == 4
    assert rec.n_samples == 1600
    assert len(rec.data_hash()) > 0


def test_simulator_provider_record():
    sim = SimulatorProvider(n_channels=8, seed=42)
    conn = sim.connect()
    assert conn.reachable
    assert conn.provider == "simulator"

    rec = sim.record(RecordRequest(channels=[0, 1, 2, 3], n_segments=2))
    assert rec.n_channels == 4
    assert rec.n_segments == 2
