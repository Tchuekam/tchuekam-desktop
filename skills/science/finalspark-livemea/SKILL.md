---
name: finalspark-livemea
description: >
  Stream live electrical activity from human brain organoids growing on
  microelectrode arrays (MEAs) at FinalSpark's laboratory in Switzerland. Use
  when the user asks about biocomputing, biological computing, wetware, brain
  organoids, neurospheres, neural cultures, MEA recordings, live neural data,
  spike detection, extracellular electrophysiology, or the FinalSpark
  NeuroPlatform. Also use to fetch microscope images of living organoids,
  electrode array geometry, or to record neural signal to HDF5 for analysis.
  No API key or account required -- the service is public.
version: 1.0.0
author: Tchuekam Agent
license: MIT
metadata:
  tchuekam:
    tags: [neuroscience, biocomputing, organoid, MEA, electrophysiology, live-data, wetware]
    related_skills: [uv, pubmed-database, bioinformatics]
prerequisites:
  commands: [uv]
---

# FinalSpark LiveMEA

Stream real electrical activity from **living human neural tissue**.

FinalSpark grows human iPSC-derived brain organoids (neurospheres, <1 mm) on
microelectrode arrays in Vevey, Switzerland, and streams their activity publicly.
This skill is a client for that stream. **No account, no API key, no auth.**

## Prerequisites

1. **`uv`**: Read the `uv` skill and follow its Setup instructions to ensure `uv`
   is installed and on PATH. All dependencies are declared inline in the script
   (PEP 723) and `uv` resolves them automatically on first run.
2. **Attribution notice**: FinalSpark asks only that users credit them as the
   source of the data. If `.licenses/finalspark_livemea_ATTRIBUTION.txt` does not
   already exist in the workspace root, (1) prominently notify the user that any
   published use of this data must credit *FinalSpark NeuroPlatform
   (https://finalspark.com)*, then (2) create the file recording the notification
   text and timestamp.

## Core Rules

- **NEVER run `python3` or `python` directly.** Always use `uv run` — the system
  Python will not have `socketio`, `numpy`, or `h5py`. Do not `pip install` or
  create venvs; `uv` manages an isolated environment from the inline metadata.
- **Always request the fewest channels needed.** Packet delivery degrades sharply
  with channel count (see Limitations). Default to 4–8 channels unless the user
  explicitly needs more.
- **Never claim the stream is gapless.** It is a throttled preview. If a user
  wants continuous recording, tell them this feed cannot provide it.
- **Always include the attribution string** in any output, report, figure caption,
  or file derived from this data.
- **This skill is read-only.** It cannot stimulate the organoids, and must never
  be extended to do so without an explicit human-approval gate — stimulation
  mutates living tissue on shared, booked hardware.

## Usage

All commands print JSON by default (machine-readable); add `--pretty` where
available for human-readable output.

### List available controllers

Always run this first — controllers go offline and into maintenance.

```bash
uv run scripts/livemea.py controllers --pretty
```

Returns each Intan controller with `online`, `maintenance`, electrode count,
MEA geometry, and whether a camera is attached. Only use controllers where
`usable` is true.

### Record live neural signal

```bash
uv run scripts/livemea.py record --channels 0-7 --packets 5 --out session.h5
```

| Flag | Meaning |
|---|---|
| `--channels` | `0-7`, `0,3,5`, or `0-3,8,12-15`. Default: 8 channels |
| `--packets` | Packets to collect. Each is 1600 samples/channel = **0.427 s** |
| `--timeout` | Seconds before giving up (default 120) |
| `--controller` | Controller id (default: service default) |
| `--out` | Save to HDF5 with full provenance metadata |

Output includes per-channel noise σ, peak amplitude, packet intervals, and a
**6σ event count** per channel.

### Electrode geometry

```bash
uv run scripts/livemea.py layout --pretty
```

Physical electrode positions in micrometres. Two geometries exist:
- **4×8** — 4 organoid sites, 3000 µm apart, 8 electrodes each on a 200 µm pitch
- **60-electrode** — 8×8 grid minus corners, plus internal reference, 200 µm pitch

### Microscope image of the organoids

```bash
uv run scripts/livemea.py capture --out mea.jpg
```

Returns the latest photo plus `taken_at` timestamp. You can literally see the
organoids sitting on the electrode sites.

### Analyse a saved recording

```bash
uv run scripts/livemea.py analyze session.h5
```

Per-channel σ, peak amplitude, 6σ event counts, and event rate per minute.

## Interpreting the data

| Property | Value |
|---|---|
| Units | **microvolts (µV)** |
| Sample rate | **3750 Hz** (30 kHz hardware, wavelet-downsampled ÷8) |
| Packet | 1600 samples/channel = 0.427 s |
| Typical noise σ | ~6–10 µV |
| Bandpass | 250–5000 Hz (applied upstream) |

Amplitude guidance from FinalSpark's own documentation:

- **< 30 µV** — likely noise
- **~50–150 µV** — plausible spike range (a spike is typically ≤100 µV, ~1 ms)
- **200–1000 µV** — almost certainly a stimulation artifact, not biology
- A perfectly regular signal with constant amplitude and frequency is **noise**,
  not an organoid — often an electrode the organoid does not fully cover

An "event" here means a 6σ threshold crossing with a 3 ms refractory window —
the same definition FinalSpark uses. **This is not spike sorting.** At 3750 Hz,
3 ms is only ~11 samples, so events merge during bursts. Do not report event
counts as spike counts.

## Limitations — state these plainly to users

- **Not gapless.** Delivery is variable and load-dependent. Measured intervals:
  4 ch → 0.6–5 s; 8 ch → ~1.5 s; 32 ch → up to ~20 s. Payloads are JSON text
  against a 1 MB server ceiling, so 32 channels is near the maximum possible.
- **No stimulation.** Read-only. Stimulation requires a paid NeuroPlatform token,
  a booking window, and the private `neuroplatformv2` SDK.
- **Undocumented endpoint.** `livenp.finalspark.com` is the service behind
  FinalSpark's public live view, but is not formally documented. It may change or
  disappear without notice — FinalSpark's own client libraries already broke this
  way. If commands start failing, the protocol likely moved.
- **Organoids die.** Cultures live 2–12 weeks on an MEA and are replaced. Activity
  declines with age. A quiet channel may mean a dead culture, not a bug.
- **Not every electrode has tissue on it.** Organoids are spherical and may not
  cover a site. Constant noise on a channel usually means poor contact.

## Attribution

Any published use of this data must credit:

> Data source: FinalSpark NeuroPlatform (https://finalspark.com)

## Protocol reference

See `references/protocol.md` for the full reverse-engineered wire protocol,
including REST endpoints, Socket.IO events, and the channel-major payload layout.
