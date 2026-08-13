"""Deterministic synthetic neural provider.

PURPOSE: this is a TEST INSTRUMENT, not a biophysical model. It exists so the
whole pipeline -- record -> preprocess -> detect -> features -> decode -> benchmark
-- can be exercised deterministically, with ground-truth labels, without touching
shared living hardware.

It deliberately does NOT claim biological realism. It has no membrane equations,
no synapses, no plasticity. If we later need realism, Brian2 / NEST / Norse would
go behind this same interface as a separate provider; nothing above this layer
would change. No such dependency is installed today because nothing needs it yet.

What it DOES model, because the pipeline must handle it:
  - per-channel background firing at configurable rates
  - biphasic spike waveforms with amplitude jitter
  - per-channel Gaussian noise at configurable sigma
  - burst episodes (temporal correlation within a channel)
  - a shared latent drive (correlation ACROSS channels)
  - stimulus-conditioned responses with class-specific latency and gain,
    which is what gives us ground-truth labels
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from biocompute.core.capabilities import Capability, ProviderCapabilities
from biocompute.core.provider import BioComputeProvider, ConnectionInfo
from biocompute.core.schema import (
    ChannelLayout,
    DeviceInfo,
    ElectrodePosition,
    Recording,
    RecordRequest,
)

DEFAULT_SAMPLE_RATE = 3750.0
"""Matches FinalSpark's public feed so pipelines are directly comparable."""


class SimulatorProvider(BioComputeProvider):
    """Synthetic, seeded, reproducible neural data."""

    name = "simulator"
    capabilities = ProviderCapabilities.of(
        Capability.RECORDING,
        Capability.STREAMING,
        Capability.LAYOUT,
        Capability.METADATA,
    )
    read_only = True
    shared_resource = False

    def __init__(
        self,
        n_channels: int = 8,
        sample_rate_hz: float = DEFAULT_SAMPLE_RATE,
        samples_per_segment: int = 1600,
        seed: int = 0,
        noise_sigma_uv: float | tuple[float, float] = (6.0, 10.0),
        base_rate_hz: float | tuple[float, float] = (0.5, 6.0),
        spike_amplitude_uv: float = 70.0,
        burst_probability: float = 0.05,
        burst_rate_multiplier: float = 12.0,
        shared_drive_strength: float = 0.15,
    ):
        self.n_channels = n_channels
        self.sample_rate_hz = sample_rate_hz
        self.samples_per_segment = samples_per_segment
        self.seed = seed
        self.spike_amplitude_uv = spike_amplitude_uv
        self.burst_probability = burst_probability
        self.burst_rate_multiplier = burst_rate_multiplier
        self.shared_drive_strength = shared_drive_strength

        rng = np.random.default_rng(seed)
        self.noise_sigma = self._spread(noise_sigma_uv, n_channels, rng)
        self.base_rate = self._spread(base_rate_hz, n_channels, rng)

    @staticmethod
    def _spread(value, n: int, rng: np.random.Generator) -> np.ndarray:
        if isinstance(value, (int, float)):
            return np.full(n, float(value))
        lo, hi = value
        return rng.uniform(lo, hi, size=n)

    # -------------------------------------------------------------- config

    def config(self) -> dict:
        return {
            "n_channels": self.n_channels,
            "sample_rate_hz": self.sample_rate_hz,
            "samples_per_segment": self.samples_per_segment,
            "seed": self.seed,
            "noise_sigma_uv": [round(float(s), 3) for s in self.noise_sigma],
            "base_rate_hz": [round(float(r), 3) for r in self.base_rate],
            "spike_amplitude_uv": self.spike_amplitude_uv,
            "burst_probability": self.burst_probability,
            "burst_rate_multiplier": self.burst_rate_multiplier,
            "shared_drive_strength": self.shared_drive_strength,
        }

    # ------------------------------------------------------------ provider

    def connect(self) -> ConnectionInfo:
        return ConnectionInfo(
            provider=self.name,
            reachable=True,
            detail="local synthetic generator; no network",
            metadata=self.config(),
        )

    def discover(self) -> list[DeviceInfo]:
        return [
            DeviceInfo(
                device_id="sim-0",
                name="Synthetic MEA",
                online=True,
                usable=True,
                n_channels=self.n_channels,
                geometry=f"synthetic linear ({self.n_channels} electrodes, 200um pitch)",
                default_channels=list(range(self.n_channels)),
                provider_metadata=self.config(),
            )
        ]

    def get_layout(self, device_id=None, mea_index=None) -> ChannelLayout:
        self.capabilities.require(self.name, Capability.LAYOUT)
        return ChannelLayout(
            provider=self.name,
            device_id=device_id or "sim-0",
            mea_index=mea_index or 0,
            geometry=f"synthetic linear ({self.n_channels} electrodes, 200um pitch)",
            electrodes=[
                ElectrodePosition(channel_index=i, x_um=200.0 * i, y_um=0.0, label=f"{i:02d}")
                for i in range(self.n_channels)
            ],
        )

    def get_sample_metadata(self, device_id=None) -> dict:
        self.capabilities.require(self.name, Capability.METADATA)
        return {
            "sample_type": "synthetic",
            "biological": False,
            "note": "No biological sample. Generated data for pipeline testing only.",
            **self.config(),
        }

    def record(self, request: RecordRequest) -> Recording:
        """Unlabelled recording (background activity only)."""
        channels = request.channels or list(range(self.n_channels))
        self._validate_channels(channels)
        rng = np.random.default_rng(self.seed + 1000)
        segs = [
            self._make_segment(channels, rng, stimulus_class=None)
            for _ in range(request.n_segments)
        ]
        return self._package(
            np.stack(segs), channels, request.experiment_id, stimulus_metadata=None
        )

    # ------------------------------------------------------- labelled data

    def record_labeled(
        self,
        n_classes: int = 2,
        trials_per_class: int = 40,
        channels: list[int] | None = None,
        experiment_id: str = "sim-labeled",
        seed: int | None = None,
        response_gain: float = 1.0,
    ) -> Recording:
        """Generate trials with GROUND-TRUTH stimulus labels.

        One segment == one trial. Each class drives a distinct subset of channels
        with a class-specific latency and gain, so a decoder has real signal to
        find. `response_gain` scales the effect: 0.0 produces a NULL DATASET where
        classes are statistically identical, which is the correct negative control
        for any decoding claim.
        """
        channels = channels or list(range(self.n_channels))
        self._validate_channels(channels)
        rng = np.random.default_rng(self.seed + 7 if seed is None else seed)

        labels: list[int] = []
        segs: list[np.ndarray] = []
        for cls in range(n_classes):
            for _ in range(trials_per_class):
                segs.append(
                    self._make_segment(channels, rng, stimulus_class=cls, gain=response_gain)
                )
                labels.append(cls)

        order = rng.permutation(len(segs))
        data = np.stack([segs[i] for i in order])
        labels = [labels[i] for i in order]

        return self._package(
            data,
            channels,
            experiment_id,
            stimulus_metadata={
                "labels": labels,
                "n_classes": n_classes,
                "trials_per_class": trials_per_class,
                "label_source": "ground_truth_synthetic",
                "response_gain": response_gain,
                "is_null_dataset": response_gain == 0.0,
                "responsive_channels_by_class": {
                    str(c): self._responsive_channels(c, channels) for c in range(n_classes)
                },
            },
        )

    # -------------------------------------------------------------- innards

    def _validate_channels(self, channels: list[int]) -> None:
        bad = [c for c in channels if not 0 <= c < self.n_channels]
        if bad:
            raise ValueError(f"channels out of range 0..{self.n_channels - 1}: {bad}")

    def _responsive_channels(self, stimulus_class: int, channels: list[int]) -> list[int]:
        """Deterministic per-class channel subset (~half the channels)."""
        half = max(1, len(channels) // 2)
        start = (stimulus_class * half) % max(1, len(channels))
        return [channels[(start + i) % len(channels)] for i in range(half)]

    def _spike_waveform(self, rng: np.random.Generator) -> np.ndarray:
        """Biphasic spike: small positive dip, large negative trough, recovery."""
        n = max(4, int(round(0.0012 * self.sample_rate_hz)))  # ~1.2 ms
        t = np.linspace(-1.6, 2.6, n)
        w = -np.exp(-(t**2) / 0.35) + 0.32 * np.exp(-((t - 1.5) ** 2) / 1.1)
        w = w / np.abs(w).max()
        amp = self.spike_amplitude_uv * rng.uniform(0.65, 1.35)
        return (w * amp).astype(np.float32)

    def _make_segment(
        self,
        channels: list[int],
        rng: np.random.Generator,
        stimulus_class: int | None,
        gain: float = 1.0,
    ) -> np.ndarray:
        n = self.samples_per_segment
        seg = np.zeros((len(channels), n), dtype=np.float32)

        # Shared latent drive -> cross-channel correlation.
        drive = rng.normal(0.0, 1.0, size=n).astype(np.float32)
        drive = np.convolve(drive, np.ones(64) / 64, mode="same")

        responsive = (
            self._responsive_channels(stimulus_class, channels)
            if stimulus_class is not None
            else []
        )
        latency_s = 0.02 + 0.03 * (stimulus_class or 0)

        for i, ch in enumerate(channels):
            seg[i] = rng.normal(0.0, self.noise_sigma[ch % self.n_channels], size=n)
            seg[i] += self.shared_drive_strength * self.noise_sigma[ch % self.n_channels] * drive

            rate = self.base_rate[ch % self.n_channels]
            if rng.random() < self.burst_probability:
                rate *= self.burst_rate_multiplier

            n_spikes = rng.poisson(rate * n / self.sample_rate_hz)

            if stimulus_class is not None and ch in responsive and gain > 0:
                n_spikes += rng.poisson(4.0 * gain)

            for _ in range(int(n_spikes)):
                w = self._spike_waveform(rng)
                if stimulus_class is not None and ch in responsive and gain > 0:
                    centre = int(latency_s * self.sample_rate_hz)
                    jitter = int(0.008 * self.sample_rate_hz)
                    pos = int(np.clip(rng.normal(centre, jitter), 0, n - len(w) - 1))
                else:
                    pos = int(rng.integers(0, max(1, n - len(w))))
                seg[i, pos : pos + len(w)] += w

        return seg

    def _package(
        self,
        data: np.ndarray,
        channels: list[int],
        experiment_id: str,
        stimulus_metadata: dict | None,
    ) -> Recording:
        now = datetime.now(timezone.utc)
        seg_dur = self.samples_per_segment / self.sample_rate_hz
        rec = Recording(
            experiment_id=experiment_id,
            provider=self.name,
            session_id=f"sim-seed{self.seed}",
            timestamp=now.isoformat(),
            sample_rate_hz=self.sample_rate_hz,
            channels=list(channels),
            units="microvolts",
            data=data,
            segment_timestamps=[
                (now + timedelta(seconds=i * seg_dur)).isoformat() for i in range(len(data))
            ],
            contiguous=True,
            channel_layout=self.get_layout(),
            stimulus_metadata=stimulus_metadata,
            provider_metadata={"simulator_config": self.config(), "biological": False},
        )
        rec.add_processing_step("simulator.generate", **self.config())
        return rec
