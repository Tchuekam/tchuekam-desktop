"""Reusable, reproducible signal-processing pipeline.

    raw -> validate -> filter -> noise estimate -> artifact detect
        -> spike detect -> spike representation -> features

Every step records its EFFECTIVE parameters (not just the ones the caller passed)
into the Recording's `processing_parameters`, so a run can be reproduced exactly
from its manifest.

Deliberately interpretable: median-absolute-deviation noise estimation and
threshold crossing, not learned detectors. Learned methods can be added later as
additional steps, but the baseline must stay auditable.

SEGMENT SAFETY
--------------
Every step operates WITHIN segments. Nothing filters or detects across a segment
boundary, because for gappy providers (FinalSpark) consecutive segments are
separated by unknown wall-clock gaps. This is enforced by construction: the step
API receives data shaped (n_segments, n_channels, n_samples) and loops segments.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from biocompute.core.schema import Recording

MAD_TO_SIGMA = 0.6745
"""median(|x|)/0.6745 estimates sigma robustly against spikes (Quiroga et al. 2004)."""


# --------------------------------------------------------------- framework


@dataclass
class PipelineContext:
    """Carries intermediate results between steps."""

    recording: Recording
    signal: np.ndarray
    sample_rate_hz: float
    channels: list[int]
    noise_sigma: np.ndarray | None = None
    artifact_mask: np.ndarray | None = None
    spikes: SpikeTrains | None = None
    features: np.ndarray | None = None
    feature_names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PipelineStep(ABC):
    name: str = "step"

    @abstractmethod
    def params(self, ctx: PipelineContext) -> dict[str, Any]:
        """Effective parameters actually used, after defaults are resolved."""

    @abstractmethod
    def apply(self, ctx: PipelineContext) -> PipelineContext: ...


class Pipeline:
    """An ordered list of steps applied to a Recording."""

    def __init__(self, steps: list[PipelineStep]):
        self.steps = steps

    def describe(self) -> list[str]:
        return [s.name for s in self.steps]

    def run(self, recording: Recording) -> PipelineContext:
        ctx = PipelineContext(
            recording=recording,
            signal=np.array(recording.data, dtype=np.float32, copy=True),
            sample_rate_hz=recording.sample_rate_hz,
            channels=list(recording.channels),
        )
        for step in self.steps:
            ctx = step.apply(ctx)
            recording.add_processing_step(step.name, **step.params(ctx))
        if ctx.warnings:
            recording.add_processing_step("pipeline.warnings", warnings=ctx.warnings)
        return ctx


# ------------------------------------------------------------------- steps


class Validate(PipelineStep):
    """Sanity checks. Emits warnings rather than silently proceeding."""

    name = "validate"

    def __init__(self, expect_units: str = "microvolts", max_plausible_uv: float = 5000.0):
        self.expect_units = expect_units
        self.max_plausible_uv = max_plausible_uv
        self._report: dict[str, Any] = {}

    def params(self, ctx):
        return {
            "expect_units": self.expect_units,
            "max_plausible_uv": self.max_plausible_uv,
            **self._report,
        }

    def apply(self, ctx):
        rec, x = ctx.recording, ctx.signal
        nyquist = ctx.sample_rate_hz / 2.0

        if rec.units != self.expect_units:
            ctx.warnings.append(f"units are '{rec.units}', expected '{self.expect_units}'")
        if not np.isfinite(x).all():
            n_bad = int((~np.isfinite(x)).sum())
            ctx.warnings.append(f"{n_bad} non-finite samples; replaced with 0")
            ctx.signal = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        if np.abs(ctx.signal).max() > self.max_plausible_uv:
            ctx.warnings.append(
                f"peak {np.abs(ctx.signal).max():.0f} uV exceeds plausible range "
                f"{self.max_plausible_uv} uV; check units/scaling"
            )

        # Upstream band vs this recording's Nyquist. For FinalSpark the signal was
        # band-limited 250-5000 Hz BEFORE a /8 downsample to 3750 Hz, so anything
        # above 1875 Hz is aliased. Surface it rather than pretend otherwise.
        band = (rec.provider_metadata or {}).get("upstream_bandpass_hz")
        if band and band[1] > nyquist:
            ctx.warnings.append(
                f"upstream band extends to {band[1]} Hz but Nyquist here is {nyquist:.0f} Hz "
                f"-- content above Nyquist is aliased and cannot be recovered"
            )

        for ch_i, ch in enumerate(ctx.channels):
            if np.allclose(ctx.signal[:, ch_i, :], 0.0):
                ctx.warnings.append(f"channel {ch} is all zeros (dead or disconnected?)")

        self._report = {
            "n_segments": int(ctx.signal.shape[0]),
            "n_channels": int(ctx.signal.shape[1]),
            "n_samples": int(ctx.signal.shape[2]),
            "nyquist_hz": nyquist,
            "contiguous": rec.contiguous,
            "warnings": list(ctx.warnings),
        }
        return ctx


class Bandpass(PipelineStep):
    """Zero-phase Butterworth bandpass, applied per segment.

    Cutoffs are clamped below Nyquist and the clamped values are what get recorded,
    so the manifest never claims a filter that was not actually applied.
    """

    name = "bandpass"

    def __init__(self, low_hz: float = 300.0, high_hz: float | None = None, order: int = 4):
        self.low_hz = low_hz
        self.high_hz = high_hz
        self.order = order
        self._effective: dict[str, Any] = {}

    def params(self, ctx):
        return {"requested_low_hz": self.low_hz, "requested_high_hz": self.high_hz,
                "order": self.order, **self._effective}

    def apply(self, ctx):
        from scipy.signal import butter, filtfilt

        nyq = ctx.sample_rate_hz / 2.0
        high = self.high_hz if self.high_hz is not None else nyq * 0.95
        high = min(high, nyq * 0.99)
        low = max(self.low_hz, 1.0)
        if low >= high:
            ctx.warnings.append(f"bandpass skipped: low {low} >= high {high}")
            self._effective = {"applied": False}
            return ctx

        b, a = butter(self.order, [low / nyq, high / nyq], btype="band")
        out = np.empty_like(ctx.signal)
        padlen = 3 * max(len(a), len(b))
        if ctx.signal.shape[2] <= padlen:
            ctx.warnings.append("segment too short for zero-phase filtering; skipped")
            self._effective = {"applied": False}
            return ctx

        for s in range(ctx.signal.shape[0]):
            out[s] = filtfilt(b, a, ctx.signal[s], axis=-1)
        ctx.signal = out.astype(np.float32)
        self._effective = {
            "applied": True,
            "effective_low_hz": float(low),
            "effective_high_hz": float(high),
            "filter": "butterworth",
            "phase": "zero (filtfilt)",
            "nyquist_hz": nyq,
        }
        return ctx


class NormalizeAmplitude(PipelineStep):
    """Divide every (segment, channel) by its OWN robust sigma. Amplitude control.

    This is the real control for the "channels differ only in gain" confound.
    After it, every trace has unit noise sigma, so absolute amplitude and per-channel
    electrode gain carry no information at all. Detection thresholds also become
    identical across channels, equalising sensitivity.

    Anything a decoder can still exploit afterwards is structure -- event rate,
    timing, waveform shape -- not gain.

    NOTE: this is NOT the same as standardising feature columns. Column-wise
    z-scoring across samples rescales each feature globally and leaves per-channel
    mean differences fully intact, so it does not control this confound.
    """

    name = "normalize_amplitude"

    def __init__(self, method: str = "mad"):
        if method not in ("mad", "rms"):
            raise ValueError("method must be 'mad' or 'rms'")
        self.method = method
        self._report: dict[str, Any] = {}

    def params(self, ctx):
        return {
            "method": self.method,
            "scope": "per (segment, channel)",
            "effect": "unit noise sigma everywhere; absolute gain is not recoverable",
            **self._report,
        }

    def apply(self, ctx):
        x = ctx.signal
        if self.method == "mad":
            scale = np.median(np.abs(x), axis=-1, keepdims=True) / MAD_TO_SIGMA
        else:
            scale = np.sqrt(np.mean(x**2, axis=-1, keepdims=True))
        scale = np.maximum(scale, 1e-9)
        ctx.signal = (x / scale).astype(np.float32)
        self._report = {
            "scale_median": round(float(np.median(scale)), 6),
            "scale_min": round(float(scale.min()), 6),
            "scale_max": round(float(scale.max()), 6),
            "units_after": "dimensionless (sigma units)",
        }
        ctx.warnings.append(
            "amplitude normalised per segment-channel: absolute uV values and any "
            "amplitude-derived feature are no longer interpretable in microvolts"
        )
        return ctx


class EstimateNoise(PipelineStep):
    """Per-channel noise sigma. MAD by default; std is available but spike-biased."""

    name = "estimate_noise"

    def __init__(self, method: str = "mad"):
        if method not in ("mad", "std"):
            raise ValueError("method must be 'mad' or 'std'")
        self.method = method
        self._sigma: list[float] = []

    def params(self, ctx):
        return {
            "method": self.method,
            "formula": "median(|x|)/0.6745" if self.method == "mad" else "std(x)",
            "sigma_uv_per_channel": {
                str(ch): round(float(s), 4) for ch, s in zip(ctx.channels, self._sigma)
            },
        }

    def apply(self, ctx):
        x = ctx.signal
        flat = x.transpose(1, 0, 2).reshape(x.shape[1], -1)
        if self.method == "mad":
            sigma = np.median(np.abs(flat), axis=1) / MAD_TO_SIGMA
        else:
            sigma = flat.std(axis=1)
        sigma = np.maximum(sigma, 1e-9)
        ctx.noise_sigma = sigma.astype(np.float32)
        self._sigma = [float(s) for s in sigma]
        return ctx


class DetectArtifacts(PipelineStep):
    """Flag samples too large to be biological.

    FinalSpark's guidance: amplitudes of 200-1000 uV are almost certainly
    stimulation or electrical artifact, not organoid activity.
    """

    name = "detect_artifacts"

    def __init__(self, absolute_uv: float = 200.0, sigma_multiple: float | None = 20.0,
                 dilate_ms: float = 2.0):
        self.absolute_uv = absolute_uv
        self.sigma_multiple = sigma_multiple
        self.dilate_ms = dilate_ms
        self._report: dict[str, Any] = {}

    def params(self, ctx):
        return {"absolute_uv": self.absolute_uv, "sigma_multiple": self.sigma_multiple,
                "dilate_ms": self.dilate_ms, **self._report}

    def apply(self, ctx):
        x = ctx.signal
        thr = np.full(x.shape[1], self.absolute_uv, dtype=np.float32)
        if self.sigma_multiple is not None and ctx.noise_sigma is not None:
            thr = np.minimum(thr, self.sigma_multiple * ctx.noise_sigma)

        mask = np.abs(x) > thr[None, :, None]
        w = max(1, int(round(self.dilate_ms * 1e-3 * ctx.sample_rate_hz)))
        if w > 1:
            kernel = np.ones(w, dtype=bool)
            dil = np.zeros_like(mask)
            for s in range(mask.shape[0]):
                for c in range(mask.shape[1]):
                    if mask[s, c].any():
                        dil[s, c] = np.convolve(mask[s, c].astype(np.int8), kernel, "same") > 0
                    else:
                        dil[s, c] = mask[s, c]
            mask = dil

        ctx.artifact_mask = mask
        self._report = {
            "threshold_uv_per_channel": {
                str(ch): round(float(t), 3) for ch, t in zip(ctx.channels, thr)
            },
            "artifact_fraction": round(float(mask.mean()), 6),
            "channels_with_artifacts": [
                int(ch) for i, ch in enumerate(ctx.channels) if mask[:, i, :].any()
            ],
        }
        return ctx


@dataclass
class SpikeTrains:
    """Detected events, kept per (segment, channel). Never merged across segments."""

    sample_rate_hz: float
    channels: list[int]
    n_segments: int
    n_samples: int
    #: (segment, channel) -> sample indices within that segment
    indices: dict[tuple[int, int], np.ndarray] = field(default_factory=dict)
    #: (segment, channel) -> signed peak amplitude in uV
    amplitudes: dict[tuple[int, int], np.ndarray] = field(default_factory=dict)

    @property
    def segment_duration_s(self) -> float:
        return self.n_samples / self.sample_rate_hz

    def count(self, segment: int, channel: int) -> int:
        return int(len(self.indices.get((segment, channel), ())))

    def channel_total(self, channel: int) -> int:
        return sum(self.count(s, channel) for s in range(self.n_segments))

    def total(self) -> int:
        return sum(len(v) for v in self.indices.values())

    def times_s(self, segment: int, channel: int) -> np.ndarray:
        return self.indices.get((segment, channel), np.array([])) / self.sample_rate_hz


class DetectSpikes(PipelineStep):
    """Threshold crossing with a refractory window, per segment, per channel.

    This is EVENT DETECTION, not spike sorting. It does not resolve which neuron
    produced an event, and during bursts several true spikes can merge into one
    event. Report counts as 'events', never as 'spikes'.
    """

    name = "detect_spikes"

    def __init__(self, threshold_sigma: float = 6.0, refractory_ms: float = 3.0,
                 polarity: str = "both", exclude_artifacts: bool = True):
        if polarity not in ("both", "negative", "positive"):
            raise ValueError("polarity must be 'both', 'negative' or 'positive'")
        self.threshold_sigma = threshold_sigma
        self.refractory_ms = refractory_ms
        self.polarity = polarity
        self.exclude_artifacts = exclude_artifacts
        self._report: dict[str, Any] = {}

    def params(self, ctx):
        return {
            "threshold_sigma": self.threshold_sigma,
            "refractory_ms": self.refractory_ms,
            "polarity": self.polarity,
            "exclude_artifacts": self.exclude_artifacts,
            "noise_estimator": "see estimate_noise step",
            "detection_type": "threshold_crossing (event detection, not spike sorting)",
            **self._report,
        }

    def apply(self, ctx):
        if ctx.noise_sigma is None:
            raise RuntimeError("DetectSpikes requires EstimateNoise to run first")

        x = ctx.signal
        n_seg, n_ch, n_samp = x.shape
        refr = max(1, int(round(self.refractory_ms * 1e-3 * ctx.sample_rate_hz)))
        trains = SpikeTrains(ctx.sample_rate_hz, list(ctx.channels), n_seg, n_samp)

        for s in range(n_seg):
            for c in range(n_ch):
                sig = x[s, c]
                thr = self.threshold_sigma * ctx.noise_sigma[c]
                if self.polarity == "both":
                    over = np.abs(sig) > thr
                elif self.polarity == "negative":
                    over = sig < -thr
                else:
                    over = sig > thr
                if self.exclude_artifacts and ctx.artifact_mask is not None:
                    over &= ~ctx.artifact_mask[s, c]

                idx = np.flatnonzero(over)
                kept: list[int] = []
                last = -refr
                for i in idx:
                    if i - last >= refr:
                        kept.append(int(i))
                        last = i
                if kept:
                    arr = np.array(kept, dtype=np.int64)
                    trains.indices[(s, c)] = arr
                    trains.amplitudes[(s, c)] = sig[arr]

        ctx.spikes = trains
        self._report = {
            "threshold_uv_per_channel": {
                str(ch): round(float(self.threshold_sigma * ctx.noise_sigma[i]), 3)
                for i, ch in enumerate(ctx.channels)
            },
            "refractory_samples": refr,
            "total_events": trains.total(),
            "events_per_channel": {
                str(ch): trains.channel_total(i) for i, ch in enumerate(ctx.channels)
            },
        }
        return ctx


class ExtractFeatures(PipelineStep):
    """Per-segment feature vector for decoding.

    One row per segment; features are concatenated per channel. All features are
    interpretable by construction -- no learned embeddings at this layer.
    """

    name = "extract_features"

    PER_CHANNEL = ("event_count", "event_rate_hz", "rms_uv", "mad_sigma_uv",
                   "peak_abs_uv", "mean_abs_uv", "first_event_latency_s")

    def __init__(self, standardize_features: bool = False):
        self.standardize_features = standardize_features
        self._report: dict[str, Any] = {}

    def params(self, ctx):
        return {
            "features_per_channel": list(self.PER_CHANNEL),
            "standardize_features": self.standardize_features,
            "standardize_note": (
                "column-wise z-score across samples. This is a SCALING convenience "
                "only -- it does NOT remove per-channel amplitude differences and is "
                "NOT a control for the gain confound. Use NormalizeAmplitude for that."
            ),
            **self._report,
        }

    def apply(self, ctx):
        if ctx.spikes is None:
            raise RuntimeError("ExtractFeatures requires DetectSpikes to run first")

        x, trains = ctx.signal, ctx.spikes
        n_seg, n_ch, n_samp = x.shape
        dur = n_samp / ctx.sample_rate_hz
        rows, names = [], []

        for s in range(n_seg):
            row = []
            for c in range(n_ch):
                sig = x[s, c]
                cnt = trains.count(s, c)
                idx = trains.indices.get((s, c))
                latency = float(idx[0] / ctx.sample_rate_hz) if idx is not None and len(idx) else dur
                row.extend([
                    float(cnt),
                    float(cnt / dur),
                    float(np.sqrt(np.mean(sig**2))),
                    float(np.median(np.abs(sig)) / MAD_TO_SIGMA),
                    float(np.abs(sig).max()),
                    float(np.mean(np.abs(sig))),
                    latency,
                ])
                if s == 0:
                    names.extend(f"ch{ctx.channels[c]}_{f}" for f in self.PER_CHANNEL)
            rows.append(row)

        feats = np.array(rows, dtype=np.float32)

        if self.standardize_features:
            mu, sd = feats.mean(axis=0), feats.std(axis=0)
            feats = (feats - mu) / np.maximum(sd, 1e-9)

        ctx.features = feats
        ctx.feature_names = names
        self._report = {"n_features": int(feats.shape[1]), "n_samples": int(feats.shape[0])}
        return ctx


# ------------------------------------------------------------------ presets


def default_pipeline(
    bandpass_low_hz: float = 300.0,
    threshold_sigma: float = 6.0,
    normalize_amplitude: bool = False,
    standardize_features: bool = False,
) -> Pipeline:
    """The standard interpretable pipeline used by the experiment engine.

    Set `normalize_amplitude=True` to run the amplitude control: every trace is
    scaled to unit noise sigma, so no decoder can separate channels by gain.
    """
    steps: list[PipelineStep] = [Validate(), Bandpass(low_hz=bandpass_low_hz)]
    if normalize_amplitude:
        steps.append(NormalizeAmplitude(method="mad"))
    steps += [
        EstimateNoise(method="mad"),
        DetectArtifacts(),
        DetectSpikes(threshold_sigma=threshold_sigma),
        ExtractFeatures(standardize_features=standardize_features),
    ]
    return Pipeline(steps)
