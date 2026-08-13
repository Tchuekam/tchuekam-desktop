"""FinalSpark LiveMEA as a BioCompute provider.

READ-ONLY. Public scope only. This adapter reads the endpoints that back
FinalSpark's own public live view and nothing else. It performs no authentication,
and must never be extended to bypass authentication, booking, authorisation, or
rate limits. `stimulate()` is blocked at the base class.

CAPABILITY NOTE -- why STREAMING is NOT declared
------------------------------------------------
The service does push data over a socket, but delivery is throttled and gappy
(measured: 0.6-20 s between 0.427 s packets, scaling with channel count). It does
not deliver signal continuously as produced, so declaring STREAMING would mislead
callers into assuming gapless coverage. Recordings from this provider are marked
`contiguous=False`, and `Recording.assert_contiguous()` will reject any analysis
that assumes otherwise.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
from biocompute.providers.finalspark import client


class FinalSparkProvider(BioComputeProvider):
    """Live human brain-organoid activity from FinalSpark's public service."""

    name = "finalspark"
    capabilities = ProviderCapabilities.of(
        Capability.RECORDING,
        Capability.LAYOUT,
        Capability.MICROSCOPY,
    )
    read_only = True
    shared_resource = True

    def __init__(self, max_channels: int = client.MAX_CHANNELS):
        self.max_channels = min(max_channels, client.MAX_CHANNELS)
        self._numbersample: int | None = None
        self._controllers: list[dict] | None = None

    # ------------------------------------------------------------ internals

    def _ns(self) -> int:
        if self._numbersample is None:
            self._numbersample = client.get_numbersample()
        return self._numbersample

    def _fetch_controllers(self, refresh: bool = False) -> list[dict]:
        if self._controllers is None or refresh:
            self._controllers = client.get_controllers()
        return self._controllers

    def _resolve(self, device_id: str | None) -> dict:
        controllers = self._fetch_controllers()
        if not controllers:
            raise client.FinalSparkError("service returned no controllers")
        if device_id:
            for c in controllers:
                if c["_id"] == device_id:
                    return c
            raise client.FinalSparkError(f"controller '{device_id}' not found")
        c = client.pick_controller(controllers)
        if c is None:
            raise client.FinalSparkError("no controller available")
        return c

    # ------------------------------------------------------------- provider

    def connect(self) -> ConnectionInfo:
        try:
            ns = self._ns()
            controllers = self._fetch_controllers(refresh=True)
        except client.FinalSparkError as e:
            return ConnectionInfo(provider=self.name, reachable=False, detail=str(e))
        usable = [c for c in controllers if c.get("online") and not c.get("maintenance")]
        return ConnectionInfo(
            provider=self.name,
            reachable=True,
            detail=f"{len(usable)}/{len(controllers)} controllers usable",
            metadata={
                "base_url": client.BASE_URL,
                "numbersample": ns,
                "sample_rate_hz": client.SAMPLE_RATE_HZ,
                "segment_duration_s": round(ns / client.SAMPLE_RATE_HZ, 4),
                "attribution": client.ATTRIBUTION,
            },
        )

    def discover(self) -> list[DeviceInfo]:
        out = []
        for c in self._fetch_controllers(refresh=True):
            layout = c.get("electrode_layout") or []
            out.append(
                DeviceInfo(
                    device_id=c["_id"],
                    name=c.get("name", "?"),
                    online=bool(c.get("online")),
                    usable=bool(c.get("online")) and not c.get("maintenance"),
                    n_channels=len(layout),
                    geometry=client.classify_layout(layout),
                    default_channels=list(c.get("default_electrodes") or []),
                    mea_indices=sorted({e["mea_index"] for e in layout}) or [0],
                    provider_metadata={
                        "maintenance": c.get("maintenance"),
                        "default_controller": c.get("default_controller"),
                        "channels_per_mea": c.get("channels"),
                        "recorded_file": c.get("recorded_file"),
                        "recorded_nb_channels": c.get("recorded_nb_channels"),
                        "has_camera": bool(c.get("mea_cameras")),
                    },
                )
            )
        return out

    def get_layout(self, device_id=None, mea_index=None) -> ChannelLayout:
        self.capabilities.require(self.name, Capability.LAYOUT)
        c = self._resolve(device_id)
        mea = c.get("default_mea", 0) if mea_index is None else mea_index
        electrodes = [
            ElectrodePosition(
                channel_index=e["channel_index"],
                x_um=float(e["position"]["x"]),
                y_um=float(e["position"]["y"]),
                z_um=float(e["position"].get("z", 0)),
                label=e.get("label"),
            )
            for e in (c.get("electrode_layout") or [])
            if e.get("mea_index") == mea
        ]
        electrodes.sort(key=lambda e: e.channel_index)
        return ChannelLayout(
            provider=self.name,
            device_id=c["_id"],
            mea_index=mea,
            geometry=client.classify_layout(c.get("electrode_layout") or []),
            electrodes=electrodes,
        )

    def capture_image(self, device_id=None, mea_index=None) -> bytes:
        self.capabilities.require(self.name, Capability.MICROSCOPY)
        c = self._resolve(device_id)
        mea = c.get("default_mea", 0) if mea_index is None else mea_index
        img, _meta = client.get_capture(c["_id"], mea)
        return img

    def record(self, request: RecordRequest) -> Recording:
        c = self._resolve(request.device_id)
        if c.get("maintenance"):
            raise client.FinalSparkError(f"controller '{c.get('name')}' is in maintenance")
        if not c.get("online"):
            raise client.FinalSparkError(f"controller '{c.get('name')}' is offline")

        mea = c.get("default_mea", 0) if request.mea_index is None else request.mea_index
        channels = list(request.channels or (c.get("default_electrodes") or [])[:8])
        if not channels:
            raise client.FinalSparkError("no channels selected")
        if len(channels) > self.max_channels:
            raise client.FinalSparkError(
                f"requested {len(channels)} channels; max is {self.max_channels}"
            )

        ns = self._ns()
        packets, events = client.stream_packets(
            controller_id=c["_id"],
            mea_index=mea,
            channels=channels,
            numbersample=ns,
            n_packets=request.n_segments,
            timeout_s=request.timeout_s,
        )
        if not packets:
            detail = "; ".join(events) if events else "no packets before timeout"
            raise client.FinalSparkError(f"no data received ({detail})")

        data = np.stack([p[1] for p in packets])
        stamps = [p[0].isoformat() for p in packets]

        rec = Recording(
            experiment_id=request.experiment_id,
            provider=self.name,
            session_id=f"{c['_id']}:mea{mea}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            sample_rate_hz=client.SAMPLE_RATE_HZ,
            channels=channels,
            units="microvolts",
            data=data,
            segment_timestamps=stamps,
            contiguous=False,  # see module docstring
            channel_layout=self.get_layout(c["_id"], mea),
            stimulus_metadata=None,  # read-only: no stimulus is ever applied
            provider_metadata={
                "controller_id": c["_id"],
                "controller_name": c.get("name"),
                "mea_index": mea,
                "numbersample": ns,
                "attribution": client.ATTRIBUTION,
                "biological": True,
                "sample_type": "human iPSC-derived brain organoid",
                "stream_events": events,
                "packets_requested": request.n_segments,
                "packets_received": len(packets),
                "upstream_bandpass_hz": [250, 5000],
                "upstream_downsampling": "wavelet /8 from 30 kHz",
            },
        )
        rec.add_processing_step(
            "finalspark.acquire",
            base_url=client.BASE_URL,
            controller_id=c["_id"],
            mea_index=mea,
            channels=channels,
            numbersample=ns,
            sample_rate_hz=client.SAMPLE_RATE_HZ,
            n_segments_requested=request.n_segments,
            timeout_s=request.timeout_s,
        )
        return rec
