"""Provider-neutral neural data schema.

DESIGN NOTE -- why `Recording` is segmented
--------------------------------------------
Real acquisition is often not gapless. FinalSpark's public live feed, for example,
delivers 0.427 s packets separated by variable gaps of 0.5-20 s. Concatenating
those packets into one array would silently fabricate temporal continuity that
does not exist, and every downstream ISI / burst / synchrony statistic computed
across a seam would be wrong.

So a Recording holds SEGMENTS: `data` has shape (n_segments, n_channels, n_samples)
with one wall-clock timestamp per segment, plus a `contiguous` flag. Analysis code
must operate within segments unless `contiguous` is True. `assert_contiguous()`
exists so callers fail loudly rather than quietly producing nonsense.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

SCHEMA_VERSION = "1.0.0"


@dataclass
class ElectrodePosition:
    """Physical position of one electrode, in micrometres."""

    channel_index: int
    x_um: float
    y_um: float
    z_um: float = 0.0
    label: str | None = None


@dataclass
class ChannelLayout:
    """Physical arrangement of electrodes on a device."""

    provider: str
    device_id: str
    mea_index: int
    geometry: str
    electrodes: list[ElectrodePosition] = field(default_factory=list)

    def positions(self) -> dict[int, tuple[float, float, float]]:
        return {e.channel_index: (e.x_um, e.y_um, e.z_um) for e in self.electrodes}

    def distance_um(self, ch_a: int, ch_b: int) -> float | None:
        p = self.positions()
        if ch_a not in p or ch_b not in p:
            return None
        a, b = np.array(p[ch_a]), np.array(p[ch_b])
        return float(np.linalg.norm(a - b))

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "device_id": self.device_id,
            "mea_index": self.mea_index,
            "geometry": self.geometry,
            "electrodes": [asdict(e) for e in self.electrodes],
        }


@dataclass
class ProcessingStep:
    """One applied processing step and every parameter it used.

    Recorded so an experiment can be reproduced exactly. Never omit a parameter
    because it was left at its default -- record the effective value.
    """

    name: str
    params: dict[str, Any]
    software_version: str = SCHEMA_VERSION
    applied_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Recording:
    """A provider-neutral neural recording.

    data: float32, shape (n_segments, n_channels, n_samples)
    """

    experiment_id: str
    provider: str
    session_id: str
    timestamp: str
    sample_rate_hz: float
    channels: list[int]
    units: str
    data: np.ndarray
    segment_timestamps: list[str] = field(default_factory=list)
    contiguous: bool = False
    channel_layout: ChannelLayout | None = None
    stimulus_metadata: dict[str, Any] | None = None
    processing_parameters: list[ProcessingStep] = field(default_factory=list)
    raw_data_reference: str | None = None
    processed_data_reference: str | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    # ---------------------------------------------------------------- shape

    def __post_init__(self):
        self.data = np.asarray(self.data, dtype=np.float32)
        if self.data.ndim != 3:
            raise ValueError(
                f"data must be (n_segments, n_channels, n_samples); got {self.data.shape}"
            )
        if self.data.shape[1] != len(self.channels):
            raise ValueError(
                f"data has {self.data.shape[1]} channels but `channels` lists "
                f"{len(self.channels)}"
            )
        if self.segment_timestamps and len(self.segment_timestamps) != self.n_segments:
            raise ValueError("segment_timestamps length must match n_segments")

    @property
    def n_segments(self) -> int:
        return int(self.data.shape[0])

    @property
    def n_channels(self) -> int:
        return int(self.data.shape[1])

    @property
    def n_samples(self) -> int:
        return int(self.data.shape[2])

    @property
    def segment_duration_s(self) -> float:
        return self.n_samples / self.sample_rate_hz

    @property
    def duration_s(self) -> float:
        """Total SIGNAL duration. Not wall-clock span -- gaps are excluded."""
        return self.n_segments * self.segment_duration_s

    @property
    def wall_clock_span_s(self) -> float | None:
        """Wall-clock span from first to last segment, or None if unknown."""
        if len(self.segment_timestamps) < 2:
            return None
        t0 = datetime.fromisoformat(self.segment_timestamps[0])
        t1 = datetime.fromisoformat(self.segment_timestamps[-1])
        return (t1 - t0).total_seconds() + self.segment_duration_s

    @property
    def duty_cycle(self) -> float | None:
        """Fraction of wall-clock time actually covered by signal."""
        span = self.wall_clock_span_s
        if not span:
            return None
        return self.duration_s / span

    def channel_data(self, channel: int) -> np.ndarray:
        """All segments for one channel, shape (n_segments, n_samples)."""
        if channel not in self.channels:
            raise KeyError(f"channel {channel} not in recording {self.channels}")
        return self.data[:, self.channels.index(channel), :]

    def assert_contiguous(self, operation: str) -> None:
        """Fail loudly if an operation assumes continuity this recording lacks."""
        if not self.contiguous and self.n_segments > 1:
            raise ValueError(
                f"'{operation}' requires a contiguous recording, but this one has "
                f"{self.n_segments} segments with gaps between them. Operate per-segment "
                f"instead, or record from a provider that guarantees continuity."
            )

    # ------------------------------------------------------------ provenance

    def add_processing_step(self, name: str, **params) -> None:
        self.processing_parameters.append(ProcessingStep(name=name, params=params))

    def data_hash(self) -> str:
        """Content hash of the sample data, for provenance."""
        return hashlib.sha256(np.ascontiguousarray(self.data).tobytes()).hexdigest()[:16]

    # --------------------------------------------------------- serialisation

    def metadata_dict(self) -> dict:
        """Everything except the sample array."""
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "provider": self.provider,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "units": self.units,
            "n_segments": self.n_segments,
            "n_channels": self.n_channels,
            "n_samples": self.n_samples,
            "n_samples_per_segment": self.n_samples,

            "segment_duration_s": round(self.segment_duration_s, 6),
            "duration_s": round(self.duration_s, 6),
            "wall_clock_span_s": self.wall_clock_span_s,
            "duty_cycle": self.duty_cycle,
            "contiguous": self.contiguous,
            "segment_timestamps": self.segment_timestamps,
            "channel_layout": self.channel_layout.to_dict() if self.channel_layout else None,
            "stimulus_metadata": self.stimulus_metadata,
            "processing_parameters": [asdict(s) for s in self.processing_parameters],
            "raw_data_reference": self.raw_data_reference,
            "processed_data_reference": self.processed_data_reference,
            "provider_metadata": self.provider_metadata,
            "data_hash": self.data_hash(),
        }

    def to_hdf5(self, path: str) -> str:
        import h5py

        with h5py.File(path, "w") as f:
            f.attrs["metadata_json"] = json.dumps(self.metadata_dict())
            f.create_dataset("data", data=self.data, compression="gzip")
        self.raw_data_reference = str(path)
        return str(path)

    def to_neo(self):
        """Export recording as a standardized Neo Block/Segment/AnalogSignal object."""
        try:
            import neo
            import quantities as pq
        except ImportError:
            raise ImportError("Neo integration requires `pip install neo quantities`.")

        block = neo.Block(name=self.experiment_id, description=f"Provider: {self.provider}")
        for s_idx in range(self.n_segments):
            seg_time = self.segment_timestamps[s_idx] if s_idx < len(self.segment_timestamps) else self.timestamp
            segment = neo.Segment(name=f"Segment_{s_idx}", rec_datetime=datetime.fromisoformat(seg_time))
            signal = neo.AnalogSignal(
                self.data[s_idx].T * pq.uV,
                sampling_rate=self.sample_rate_hz * pq.Hz,
                units="uV",
                name=f"Segment_{s_idx}_Signal"
            )
            segment.analogsignals.append(signal)
            block.segments.append(segment)
        return block

    @classmethod
    def from_hdf5(cls, path: str) -> Recording:
        import h5py

        with h5py.File(path, "r") as f:
            meta = json.loads(f.attrs["metadata_json"])
            data = f["data"][:]
        layout = None
        if meta.get("channel_layout"):
            cl = meta["channel_layout"]
            layout = ChannelLayout(
                provider=cl["provider"],
                device_id=cl["device_id"],
                mea_index=cl["mea_index"],
                geometry=cl["geometry"],
                electrodes=[ElectrodePosition(**e) for e in cl["electrodes"]],
            )
        return cls(
            experiment_id=meta["experiment_id"],
            provider=meta["provider"],
            session_id=meta["session_id"],
            timestamp=meta["timestamp"],
            sample_rate_hz=meta["sample_rate_hz"],
            channels=meta["channels"],
            units=meta["units"],
            data=data,
            segment_timestamps=meta.get("segment_timestamps", []),
            contiguous=meta.get("contiguous", False),
            channel_layout=layout,
            stimulus_metadata=meta.get("stimulus_metadata"),
            processing_parameters=[
                ProcessingStep(**s) for s in meta.get("processing_parameters", [])
            ],
            raw_data_reference=str(path),
            processed_data_reference=meta.get("processed_data_reference"),
            provider_metadata=meta.get("provider_metadata", {}),
            schema_version=meta.get("schema_version", SCHEMA_VERSION),
        )


@dataclass
class DeviceInfo:
    """One addressable acquisition device advertised by a provider."""

    device_id: str
    name: str
    online: bool
    usable: bool
    n_channels: int
    geometry: str = "unknown"
    default_channels: list[int] = field(default_factory=list)
    mea_indices: list[int] = field(default_factory=lambda: [0])
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecordRequest:
    """A bounded request for signal. Providers must respect these limits."""

    device_id: str | None = None
    mea_index: int | None = None
    channels: list[int] | None = None
    n_segments: int = 2
    timeout_s: float = 120.0
    experiment_id: str = "adhoc"
