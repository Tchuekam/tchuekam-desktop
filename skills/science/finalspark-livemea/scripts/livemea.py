#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "python-socketio[asyncio_client]>=5.11",
#     "aiohttp>=3.9",
#     "numpy>=1.26",
#     "h5py>=3.10",
# ]
# ///
"""
livemea.py -- stream live human neural activity from FinalSpark's public MEA service.

FinalSpark grows human iPSC-derived brain organoids on microelectrode arrays (MEAs)
in Switzerland and streams their electrical activity publicly. This script is a
client for that stream. No account, no API key, no authentication.

PROTOCOL
--------
Reverse-engineered from https://livenp.finalspark.com/client/ and verified against
the live service. FinalSpark's own client libraries (LiveMEA, LiveMEA_rs, LiveMEA_ts)
target an older service that now returns HTTP 502; this implements the current one.

    Base: https://livenp.finalspark.com   (Socket.IO v4 + same-origin REST)

    GET  /sample                                     -> {"numbersample": 1600}
    GET  /controllers                                -> {"controllers": [...]}
    GET  /controllers/{id}/meas/{m}/capture          -> image/jpeg
    GET  /controllers/{id}/meas/{m}/capture/metadata -> {"taken_at", ...}

    emit "start" {"id_intan": str, "mea_index": int, "channel_index": [int]}
    on   "data"  -> flat JSON float array, CHANNEL-MAJOR:
                    data[i*numbersample : (i+1)*numbersample] == channel_index[i]
    on   "maintenance" -> maintenance state change

    Units: microvolts.  Sample rate: 3750 Hz (30 kHz hardware, wavelet-downsampled /8).
    One packet = 1600 samples/channel = 0.4267 s of signal.

MEASURED BEHAVIOUR -- read this before designing anything
---------------------------------------------------------
The feed is a PREVIEW, not a gapless recording. Delivery is variable and scales
badly with channel count, because payloads are JSON text rather than binary.
Observed across several runs (server load clearly matters -- re-measure, do not
treat these as a spec):

      4 channels -> 0.6 s to 5 s between packets
      8 channels -> ~1.5 s
     32 channels -> up to ~20 s  (~970 KB JSON vs the 1 MB server maxPayload)

One packet carries 0.427 s of signal, so even at best you are near but not at
real time, and gaps are common. Request the FEWEST channels you actually need,
and never assume continuous coverage.

ATTRIBUTION
-----------
FinalSpark asks only that you credit them as the source of the data. Do it.

USAGE
-----
    uv run livemea.py controllers
    uv run livemea.py layout --controller <id>
    uv run livemea.py record --channels 0-7 --packets 3 --out session.h5
    uv run livemea.py capture --out mea.jpg
    uv run livemea.py analyze session.h5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import numpy as np

BASE_URL = "https://livenp.finalspark.com"
SAMPLE_RATE_HZ = 3750.0
ATTRIBUTION = "Data source: FinalSpark NeuroPlatform (https://finalspark.com)"
_UA = {"User-Agent": "tchuekam-agent/finalspark-livemea", "Accept": "application/json"}


# ------------------------------------------------------------------ helpers


def _fail(msg: str, code: int = 1):
    print(json.dumps({"ok": False, "error": msg}), file=sys.stderr)
    sys.exit(code)


def _get(path: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(BASE_URL + path, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        _fail(f"HTTP {e.code} for {path} -- the service may be down or moved")
    except Exception as e:  # noqa: BLE001
        _fail(f"{type(e).__name__} for {path}: {e}")


def _get_json(path: str, timeout: float = 30.0):
    return json.loads(_get(path, timeout))


def parse_channels(spec: str) -> list[int]:
    """'0-7'  '0,3,5'  '0-3,8,12-15'  ->  sorted unique ints."""
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a), int(b)
            if lo > hi:
                _fail(f"bad channel range '{part}'")
            out.update(range(lo, hi + 1))
        else:
            out.add(int(part))
    if not out:
        _fail("no channels selected")
    return sorted(out)


def get_numbersample() -> int:
    return int(_get_json("/sample")["numbersample"])


def get_controllers() -> list[dict]:
    return _get_json("/controllers")["controllers"]


def pick_controller(controllers: list[dict]) -> dict | None:
    """Same selection rule as FinalSpark's own web client."""
    for c in controllers:
        if c.get("default_controller") and c.get("online"):
            return c
    for c in controllers:
        if c.get("online"):
            return c
    return controllers[0] if controllers else None


def resolve_controller(controller_id: str | None) -> dict:
    controllers = get_controllers()
    if not controllers:
        _fail("no controllers returned by the service")
    if controller_id:
        for c in controllers:
            if c["_id"] == controller_id:
                return c
        _fail(f"controller '{controller_id}' not found -- run `controllers` to list them")
    c = pick_controller(controllers)
    if c is None:
        _fail("no controller available")
    return c


# ------------------------------------------------------------------ commands


def cmd_controllers(args):
    """Inventory of every Intan controller: status, geometry, cameras."""
    ns = get_numbersample()
    controllers = get_controllers()
    rows = []
    for c in controllers:
        layout = c.get("electrode_layout") or []
        rows.append(
            {
                "id": c["_id"],
                "name": c.get("name"),
                "online": c.get("online"),
                "maintenance": c.get("maintenance"),
                "default": c.get("default_controller"),
                "default_mea": c.get("default_mea"),
                "channels_per_mea": c.get("channels"),
                "n_electrodes": len(layout),
                "geometry": _classify_layout(layout),
                "default_electrodes": c.get("default_electrodes"),
                "has_camera": bool(c.get("mea_cameras")),
                "usable": bool(c.get("online")) and not c.get("maintenance"),
            }
        )
    result = {
        "ok": True,
        "numbersample": ns,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "packet_duration_s": round(ns / SAMPLE_RATE_HZ, 4),
        "n_controllers": len(rows),
        "controllers": rows,
        "attribution": ATTRIBUTION,
    }
    if args.pretty:
        print(f"numbersample={ns}  ({ns / SAMPLE_RATE_HZ:.3f} s per packet @ {SAMPLE_RATE_HZ:g} Hz)\n")
        hdr = f"{'name':10s} {'online':7s} {'maint':6s} {'elec':5s} {'geometry':25s} {'cam':4s} id"
        print(hdr)
        print("-" * len(hdr))
        for r in rows:
            print(
                f"{str(r['name']):10s} {str(r['online']):7s} {str(r['maintenance']):6s} "
                f"{str(r['n_electrodes']):5s} {r['geometry']:25s} "
                f"{'yes' if r['has_camera'] else 'no':4s} {r['id']}"
            )
        print(f"\n{ATTRIBUTION}")
    else:
        print(json.dumps(result, indent=2))


def _classify_layout(layout: list[dict]) -> str:
    """Name the MEA geometry from its electrode coordinates."""
    if not layout:
        return "unknown"
    xs = sorted({e["position"]["x"] for e in layout})
    n = len(layout)
    if n == 32 and len(xs) == 16:
        return "4x8 (4 sites, 3000um)"
    if n == 60:
        return "60-electrode (8x8-4+ref)"
    return f"{n} electrodes"


def cmd_layout(args):
    """Physical electrode coordinates in micrometres."""
    c = resolve_controller(args.controller)
    mea = args.mea if args.mea is not None else c.get("default_mea", 0)
    elecs = [
        {
            "channel_index": e["channel_index"],
            "label": e.get("label"),
            "x_um": e["position"]["x"],
            "y_um": e["position"]["y"],
            "z_um": e["position"].get("z", 0),
        }
        for e in (c.get("electrode_layout") or [])
        if e.get("mea_index") == mea
    ]
    elecs.sort(key=lambda e: e["channel_index"])
    result = {
        "ok": True,
        "controller": c["_id"],
        "name": c.get("name"),
        "mea_index": mea,
        "geometry": _classify_layout(c.get("electrode_layout") or []),
        "n_electrodes": len(elecs),
        "electrodes": elecs,
        "attribution": ATTRIBUTION,
    }
    if args.pretty:
        print(f"{c.get('name')} / MEA {mea} -- {result['geometry']}, {len(elecs)} electrodes\n")
        for e in elecs:
            print(f"  ch {e['channel_index']:3d} ({e['label']})  x={e['x_um']:6d}um  y={e['y_um']:5d}um")
        print(f"\n{ATTRIBUTION}")
    else:
        print(json.dumps(result, indent=2))


async def _stream(controller_id, mea_index, channels, numbersample, n_packets, timeout_s):
    import socketio  # imported late so `controllers` works without the extra

    packets: list[tuple[datetime, np.ndarray]] = []
    errors: list[str] = []
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
            errors.append(f"expected {expected} floats, got {flat.size}")
            return
        packets.append((datetime.now(timezone.utc), flat.reshape(len(channels), numbersample)))

    @sio.on("maintenance")
    async def on_maintenance(payload):
        errors.append(f"maintenance event: {payload}")

    await sio.connect(BASE_URL, transports=["websocket"])
    deadline = time.time() + timeout_s
    try:
        while len(packets) < n_packets and time.time() < deadline:
            await asyncio.sleep(0.1)
    finally:
        await sio.disconnect()
    return packets, errors


def cmd_record(args):
    """Stream live neural signal and optionally save it."""
    c = resolve_controller(args.controller)
    if c.get("maintenance"):
        _fail(f"controller '{c.get('name')}' is in maintenance -- pick another")
    if not c.get("online"):
        _fail(f"controller '{c.get('name')}' is offline -- pick another")

    mea = args.mea if args.mea is not None else c.get("default_mea", 0)
    channels = (
        parse_channels(args.channels)
        if args.channels
        else list(c.get("default_electrodes") or range(8))
    )
    if len(channels) > 32:
        _fail("max 32 channels per request (server payload ceiling is ~1 MB of JSON)")
    if len(channels) > 8:
        print(
            f"warning: {len(channels)} channels will be slow "
            f"(~20 s/packet at 32ch). Fewer channels = faster packets.",
            file=sys.stderr,
        )

    ns = get_numbersample()
    packets, errors = asyncio.run(
        _stream(c["_id"], mea, channels, ns, args.packets, args.timeout)
    )

    if not packets:
        _fail(
            f"no data in {args.timeout}s. "
            + ("; ".join(errors) if errors else "Try fewer channels or a longer --timeout.")
        )

    stack = np.stack([p[1] for p in packets])  # (packets, channels, samples)
    times = [p[0] for p in packets]
    intervals = [round((times[i + 1] - times[i]).total_seconds(), 3) for i in range(len(times) - 1)]

    if args.out:
        _save_h5(args.out, packets, channels, ns, c, mea)

    result = {
        "ok": True,
        "controller": {"id": c["_id"], "name": c.get("name")},
        "mea_index": mea,
        "channels": channels,
        "packets_received": len(packets),
        "packets_requested": args.packets,
        "shape": list(stack.shape),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "signal_seconds": round(len(packets) * ns / SAMPLE_RATE_HZ, 3),
        "packet_intervals_s": intervals,
        "stats_uv": {
            "mean_std": round(float(stack.std(axis=2).mean()), 2),
            "min": round(float(stack.min()), 1),
            "max": round(float(stack.max()), 1),
        },
        "per_channel_std_uv": {
            str(ch): round(float(stack[:, i, :].std()), 2) for i, ch in enumerate(channels)
        },
        "events_6sigma": _events_summary(stack, channels),
        "saved_to": args.out,
        "warnings": errors or None,
        "attribution": ATTRIBUTION,
    }
    print(json.dumps(result, indent=2))


def _events_summary(stack: np.ndarray, channels: list[int]) -> dict:
    """6-sigma threshold crossings with a 3 ms refractory window, per channel.

    Mirrors how FinalSpark defines an 'event': a crossing of 6*std(noise), after
    which 3 ms is recorded as one event. NOT spike sorting -- at 3750 Hz, 3 ms is
    only ~11 samples.
    """
    refr = max(1, int(round(0.003 * SAMPLE_RATE_HZ)))
    counts: dict[str, int] = {}
    for i, ch in enumerate(channels):
        total = 0
        for p in range(stack.shape[0]):
            x = stack[p, i, :]
            thr = 6.0 * x.std()
            last = -refr
            for idx in np.flatnonzero(np.abs(x) > thr):
                if idx - last >= refr:
                    total += 1
                    last = idx
        if total:
            counts[str(ch)] = total
    return counts


def _save_h5(path, packets, channels, numbersample, controller, mea_index):
    import h5py

    with h5py.File(path, "w") as f:
        f.attrs["source"] = ATTRIBUTION
        f.attrs["service_url"] = BASE_URL
        f.attrs["sample_rate_hz"] = SAMPLE_RATE_HZ
        f.attrs["numbersample"] = numbersample
        f.attrs["controller_id"] = controller["_id"]
        f.attrs["controller_name"] = controller.get("name", "")
        f.attrs["mea_index"] = mea_index
        f.attrs["channels"] = np.array(channels, dtype=np.int32)
        f.attrs["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
        f.attrs["units"] = "microvolts"
        for ts, arr in packets:
            g = f.create_group(ts.isoformat())
            for i, ch in enumerate(channels):
                g.create_dataset(f"electrode_{ch}", data=arr[i], compression="gzip")


def cmd_capture(args):
    """Download the latest microscope image of the organoids on an MEA."""
    c = resolve_controller(args.controller)
    mea = args.mea if args.mea is not None else c.get("default_mea", 0)
    t = int(time.time())
    meta = _get_json(f"/controllers/{c['_id']}/meas/{mea}/capture/metadata?t={t}")
    img = _get(f"/controllers/{c['_id']}/meas/{mea}/capture?t={t}", timeout=60)
    out = args.out or "mea_capture.jpg"
    with open(out, "wb") as fh:
        fh.write(img)
    print(
        json.dumps(
            {
                "ok": True,
                "saved_to": out,
                "bytes": len(img),
                "controller": c.get("name"),
                "mea_index": mea,
                "taken_at": meta.get("taken_at"),
                "camera_id": meta.get("camera_id"),
                "attribution": ATTRIBUTION,
            },
            indent=2,
        )
    )


def cmd_analyze(args):
    """Event detection and summary statistics over a saved .h5 recording."""
    import h5py

    with h5py.File(args.path, "r") as f:
        fs = float(f.attrs.get("sample_rate_hz", SAMPLE_RATE_HZ))
        channels = [int(c) for c in f.attrs.get("channels", [])]
        groups = sorted(f.keys())
        if not groups:
            _fail("file contains no packets")
        arrs = []
        for g in groups:
            arrs.append(np.stack([f[g][f"electrode_{ch}"][:] for ch in channels]))
        stack = np.stack(arrs)
        meta = {
            "controller_name": str(f.attrs.get("controller_name", "")),
            "recorded_at_utc": str(f.attrs.get("recorded_at_utc", "")),
            "source": str(f.attrs.get("source", "")),
        }

    events = _events_summary(stack, channels)
    total_s = stack.shape[0] * stack.shape[2] / fs
    print(
        json.dumps(
            {
                "ok": True,
                "file": args.path,
                "meta": meta,
                "packets": stack.shape[0],
                "channels": channels,
                "samples_per_packet": stack.shape[2],
                "sample_rate_hz": fs,
                "signal_seconds": round(total_s, 3),
                "per_channel_std_uv": {
                    str(ch): round(float(stack[:, i, :].std()), 2)
                    for i, ch in enumerate(channels)
                },
                "per_channel_peak_uv": {
                    str(ch): round(float(np.abs(stack[:, i, :]).max()), 1)
                    for i, ch in enumerate(channels)
                },
                "events_6sigma": events,
                "event_rate_per_min": {
                    ch: round(n / total_s * 60, 1) for ch, n in events.items()
                },
                "attribution": ATTRIBUTION,
            },
            indent=2,
        )
    )


# --------------------------------------------------------------------- main


def main():
    p = argparse.ArgumentParser(
        prog="livemea.py",
        description="Stream live human neural activity from FinalSpark's public MEA service.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c1 = sub.add_parser("controllers", help="list available controllers and their status")
    c1.add_argument("--pretty", action="store_true", help="human-readable table")
    c1.set_defaults(func=cmd_controllers)

    c2 = sub.add_parser("layout", help="electrode coordinates in micrometres")
    c2.add_argument("--controller", help="controller id (default: service default)")
    c2.add_argument("--mea", type=int, help="MEA index (default: controller default)")
    c2.add_argument("--pretty", action="store_true")
    c2.set_defaults(func=cmd_layout)

    c3 = sub.add_parser("record", help="stream live signal")
    c3.add_argument("--controller", help="controller id (default: service default)")
    c3.add_argument("--mea", type=int, help="MEA index")
    c3.add_argument("--channels", help="e.g. '0-7' or '0,3,5' (default: 8 channels)")
    c3.add_argument("--packets", type=int, default=2, help="packets to collect (default 2)")
    c3.add_argument("--timeout", type=float, default=120.0, help="seconds (default 120)")
    c3.add_argument("--out", help="save to .h5")
    c3.set_defaults(func=cmd_record)

    c4 = sub.add_parser("capture", help="download microscope image of the organoids")
    c4.add_argument("--controller", help="controller id")
    c4.add_argument("--mea", type=int, help="MEA index")
    c4.add_argument("--out", help="output path (default mea_capture.jpg)")
    c4.set_defaults(func=cmd_capture)

    c5 = sub.add_parser("analyze", help="analyse a saved .h5 recording")
    c5.add_argument("path")
    c5.set_defaults(func=cmd_analyze)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
