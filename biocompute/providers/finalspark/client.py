"""Protocol client for FinalSpark's public live MEA service.

RELATIONSHIP TO THE SKILL SCRIPT
--------------------------------
`skills/science/finalspark-livemea/scripts/livemea.py` is the standalone,
agent-facing CLI. It runs in an isolated `uv` environment with PEP 723 inline
dependencies and deliberately has NO import dependency on this repository, so it
keeps working regardless of the state of the main package.

This module is the importable library form used by BioCompute. The protocol
constants are therefore duplicated on purpose. `tests/biocompute/test_finalspark_
protocol_parity.py` asserts the two stay in agreement, so drift fails CI rather
than silently producing two different clients.

Full protocol reference: skills/science/finalspark-livemea/references/protocol.md

SCOPE OF USE
------------
This client only reads endpoints that back FinalSpark's own public live view. It
performs no authentication, sends no credentials, and must never be extended to
bypass authentication, booking, authorisation, or rate limits. It cannot stimulate.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import numpy as np

BASE_URL = "https://livenp.finalspark.com"
SAMPLE_RATE_HZ = 3750.0
ATTRIBUTION = "Data source: FinalSpark NeuroPlatform (https://finalspark.com)"
MAX_CHANNELS = 32
"""Server maxPayload is 1,000,000 bytes of JSON; 32ch x 1600 samples is at the ceiling."""

_UA = {"User-Agent": "tchuekam-biocompute/1.0", "Accept": "application/json"}


class FinalSparkError(RuntimeError):
    pass


def _get(path: str, timeout: float = 30.0, retries: int = 2,
         backoff_s: float = 1.5) -> bytes:
    """GET with bounded retry on transient network errors.

    This is a shared public service. Transient timeouts happen and should not be
    treated as failures, but retries stay small and backed off so we never hammer
    someone else's infrastructure. HTTP errors (4xx/5xx) are NOT retried -- those
    are answers, not transient faults.
    """
    req = urllib.request.Request(BASE_URL + path, headers=_UA)
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise FinalSparkError(f"HTTP {e.code} for {path}") from e
        except Exception as e:  # noqa: BLE001 - transient network fault
            last = e
            if attempt < retries:
                time.sleep(backoff_s * (attempt + 1))
    raise FinalSparkError(
        f"{type(last).__name__} for {path} after {retries + 1} attempts: {last}"
    ) from last


def get_json(path: str, timeout: float = 30.0):
    return json.loads(_get(path, timeout))


def get_numbersample() -> int:
    return int(get_json("/sample")["numbersample"])


def get_controllers() -> list[dict]:
    return get_json("/controllers")["controllers"]


def pick_controller(controllers: list[dict]) -> dict | None:
    """Same selection rule FinalSpark's own web client uses."""
    for c in controllers:
        if c.get("default_controller") and c.get("online"):
            return c
    for c in controllers:
        if c.get("online"):
            return c
    return controllers[0] if controllers else None


def classify_layout(layout: list[dict]) -> str:
    if not layout:
        return "unknown"
    xs = sorted({e["position"]["x"] for e in layout})
    n = len(layout)
    if n == 32 and len(xs) == 16:
        return "4x8 (4 sites, 3000um)"
    if n == 60:
        return "60-electrode (8x8-4+ref)"
    return f"{n} electrodes"


def get_capture(controller_id: str, mea_index: int = 0, timeout: float = 60.0) -> tuple[bytes, dict]:
    t = int(time.time())
    meta = get_json(f"/controllers/{controller_id}/meas/{mea_index}/capture/metadata?t={t}")
    img = _get(f"/controllers/{controller_id}/meas/{mea_index}/capture?t={t}", timeout=timeout)
    return img, meta


async def _stream_async(
    controller_id: str,
    mea_index: int,
    channels: list[int],
    numbersample: int,
    n_packets: int,
    timeout_s: float,
):
    import socketio

    packets: list[tuple[datetime, np.ndarray]] = []
    events: list[str] = []
    sio = socketio.AsyncClient(reconnection=False)

    @sio.event
    async def connect():
        await sio.emit(
            "start",
            {"id_intan": controller_id, "mea_index": mea_index, "channel_index": channels},
        )

    @sio.on("data")
    async def on_data(payload):
        flat = np.asarray(payload, dtype=np.float32)
        expected = len(channels) * numbersample
        if flat.size != expected:
            events.append(f"payload size mismatch: expected {expected}, got {flat.size}")
            return
        packets.append(
            (datetime.now(timezone.utc), flat.reshape(len(channels), numbersample))
        )

    @sio.on("maintenance")
    async def on_maintenance(payload):
        events.append(f"maintenance: {payload}")

    await sio.connect(BASE_URL, transports=["websocket"])
    deadline = time.time() + timeout_s
    try:
        while len(packets) < n_packets and time.time() < deadline:
            await asyncio.sleep(0.1)
    finally:
        # disconnect() alone leaves the underlying aiohttp session open ("Unclosed
        # client session"), which leaks sockets across repeated calls. shutdown()
        # releases it. Guarded because it is not present on every socketio version.
        try:
            await sio.disconnect()
        finally:
            shutdown = getattr(sio, "shutdown", None)
            if shutdown is not None:
                try:
                    await shutdown()
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass
    return packets, events


def stream_packets(
    controller_id: str,
    mea_index: int,
    channels: list[int],
    numbersample: int,
    n_packets: int,
    timeout_s: float = 120.0,
):
    """Collect up to `n_packets`. Each packet is 1600 samples/channel = 0.427 s.

    Delivery is variable and gappy -- callers must not assume continuity.
    """
    if len(channels) > MAX_CHANNELS:
        raise FinalSparkError(
            f"max {MAX_CHANNELS} channels per request (server JSON payload ceiling)"
        )
    return asyncio.run(
        _stream_async(controller_id, mea_index, channels, numbersample, n_packets, timeout_s)
    )
