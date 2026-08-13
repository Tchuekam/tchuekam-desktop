"""Provider interface, capability gating, simulator determinism, and the
non-negotiable safety property: no provider can stimulate."""

from __future__ import annotations

import numpy as np
import pytest

from biocompute.core.capabilities import Capability, CapabilityError, ProviderCapabilities
from biocompute.core.provider import BioComputeProvider
from biocompute.core.registry import available, get_provider
from biocompute.core.schema import RecordRequest
from biocompute.providers.simulator.adapter import SimulatorProvider


# ---------------------------------------------------------------- capabilities


def test_capabilities_membership_and_require():
    caps = ProviderCapabilities.of(Capability.RECORDING, Capability.LAYOUT)
    assert caps.supports(Capability.RECORDING)
    assert Capability.LAYOUT in caps
    assert not caps.supports(Capability.STIMULATION)
    caps.require("p", Capability.RECORDING)
    with pytest.raises(CapabilityError, match="does not support"):
        caps.require("p", Capability.STIMULATION)


def test_unsupported_capability_raises_not_fabricates(sim):
    """A provider must refuse, never invent data it cannot obtain."""
    assert not sim.capabilities.supports(Capability.MICROSCOPY)
    with pytest.raises(CapabilityError):
        sim.capture_image()
    with pytest.raises(CapabilityError):
        sim.get_environment()


# --------------------------------------------------------------------- safety


def test_no_provider_declares_stimulation():
    """Nothing in this codebase may advertise stimulation."""
    for name in available():
        p = get_provider(name)
        assert not p.capabilities.supports(Capability.STIMULATION), name
        assert p.read_only is True, name


def test_stimulate_is_blocked_at_base_class():
    for name in available():
        with pytest.raises(PermissionError, match="not implemented in BioCompute"):
            get_provider(name).stimulate()


def test_stimulate_blocked_even_for_custom_subclass():
    class Rogue(BioComputeProvider):
        name = "rogue"
        capabilities = ProviderCapabilities.of(Capability.RECORDING)

        def connect(self): ...
        def discover(self): return []
        def record(self, request): ...

    with pytest.raises(PermissionError):
        Rogue().stimulate()


# ------------------------------------------------------------------ simulator


def test_simulator_is_deterministic():
    a = SimulatorProvider(n_channels=4, seed=3).record(RecordRequest(n_segments=2))
    b = SimulatorProvider(n_channels=4, seed=3).record(RecordRequest(n_segments=2))
    assert a.data_hash() == b.data_hash()


def test_simulator_seed_changes_output():
    a = SimulatorProvider(n_channels=4, seed=3).record(RecordRequest(n_segments=2))
    b = SimulatorProvider(n_channels=4, seed=4).record(RecordRequest(n_segments=2))
    assert a.data_hash() != b.data_hash()


def test_simulator_recording_shape_and_metadata(recording):
    assert recording.data.shape == (3, 6, 800)
    assert recording.contiguous is True
    assert recording.provider_metadata["biological"] is False
    assert recording.processing_parameters[0].name == "simulator.generate"


def test_simulator_rejects_out_of_range_channels(sim):
    with pytest.raises(ValueError, match="out of range"):
        sim.record(RecordRequest(channels=[0, 99]))


def test_labeled_recording_is_balanced_and_labelled(labeled_recording):
    labels = np.array(labeled_recording.stimulus_metadata["labels"])
    assert len(labels) == labeled_recording.n_segments == 24
    assert set(np.bincount(labels).tolist()) == {12}
    assert labeled_recording.stimulus_metadata["label_source"] == "ground_truth_synthetic"


def test_null_dataset_is_flagged(null_recording):
    assert null_recording.stimulus_metadata["is_null_dataset"] is True
    assert null_recording.stimulus_metadata["response_gain"] == 0.0


def test_simulator_layout_positions(sim):
    layout = sim.get_layout()
    assert len(layout.electrodes) == 6
    assert layout.distance_um(0, 1) == pytest.approx(200.0)


# ------------------------------------------------------------------- registry


def test_registry_lists_both_providers():
    assert {"simulator", "finalspark"} <= set(available())


def test_registry_rejects_unknown():
    with pytest.raises(KeyError, match="unknown provider"):
        get_provider("does-not-exist")


def test_finalspark_capability_declaration_is_honest():
    """FinalSpark must NOT claim STREAMING: its feed is throttled and gappy."""
    p = get_provider("finalspark")
    assert p.capabilities.supports(Capability.RECORDING)
    assert p.capabilities.supports(Capability.LAYOUT)
    assert p.capabilities.supports(Capability.MICROSCOPY)
    assert not p.capabilities.supports(Capability.STREAMING)
    assert p.shared_resource is True
