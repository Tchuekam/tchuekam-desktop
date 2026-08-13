# FinalSpark LiveMEA — wire protocol reference

Reverse-engineered from the JavaScript bundle served at
`https://livenp.finalspark.com/client/` (the page embedded in
`https://finalspark.com/live/`) and verified against the live service on
**2026-08-13**.

This is not official documentation. FinalSpark has not published a spec for this
endpoint. Re-verify before depending on it.

---

## Why this document exists

FinalSpark publishes three client libraries. **All three were broken at time of
writing**, because they target a previous service:

| Repo | Host it targets | Status 2026-08-13 |
|---|---|---|
| [`LiveMEA`](https://github.com/FinalSpark-np/LiveMEA) (Python) | `livemeaservice.finalspark.com` | HTTP 502 |
| [`LiveMEA_rs`](https://github.com/FinalSpark-np/LiveMEA_rs) (Rust) | `livemeaservice2.alpvision.com` | HTTP 502 |
| [`LiveMEA_ts`](https://github.com/FinalSpark-np/LiveMEA_ts) (TypeScript) | `livemeaservice2.alpvision.com` | HTTP 502 |

The 502s come from FinalSpark's reverse proxy while `finalspark.com` itself
serves 200, so the backends behind those hostnames are gone rather than
unreachable.

---

## Base

```
https://livenp.finalspark.com
```

Socket.IO v4 and REST are served from the same origin. The client bundle builds
its API base from an empty build-time variable, so all paths are relative.

Handshake advertises:

```json
{"sid":"...","upgrades":["websocket"],"pingInterval":25000,
 "pingTimeout":20000,"maxPayload":1000000}
```

`maxPayload: 1000000` is the practical channel-count ceiling — see *Throughput*.

---

## REST

### `GET /sample`

```json
{"numbersample": 1600}
```

Samples per channel in each `data` packet. Was **4096** on the old service.

### `GET /controllers`

```json
{"controllers": [
  {
    "_id": "6a2690e103b588f428c382e7",
    "name": "Intan",
    "address": "172.30.1.10:5051",
    "online": true,
    "maintenance": false,
    "default_controller": true,
    "default_mea": 0,
    "default_electrodes": [0, 1, ..., 31],
    "channels": [32, 0, 0, 0],
    "recorded_file": "wavelet_signal.bin",
    "recorded_nb_channels": 128,
    "mea_cameras": [{"mea_index": 0, "camera_id": 4}],
    "electrode_layout": [
      {"mea_index":0, "channel_index":0,
       "position":{"x":200,"y":400,"z":0}, "label":"00"}
    ]
  }
]}
```

| Field | Meaning |
|---|---|
| `_id` | Pass as `id_intan` when subscribing |
| `address` | Internal LAN address of the Intan software host |
| `channels` | Channel count per MEA slot, e.g. `[32,0,0,0]` = 32 on MEA 0 |
| `recorded_file` | `wavelet_signal.bin` — the downsampled stream |
| `recorded_nb_channels` | 128 (global electrode index 0–127) |
| `electrode_layout` | Physical positions in **micrometres** |

Client-side controller selection: first `default_controller && online`, else
first `online`, else first entry.

### `GET /controllers/{id}/meas/{mea}/capture`

`image/jpeg` — latest microscope photo of that MEA. ~170 KB typical.

### `GET /controllers/{id}/meas/{mea}/capture/metadata`

```json
{"controller_id":"...","mea_index":0,"camera_id":4,
 "capture_id":"...","taken_at":"2026-08-13T14:55:49.784Z"}
```

The client refreshes `?t=` hourly (UTC hour bucket), so images update on
roughly that cadence.

### Removed endpoints

`/check`, `/islive`, `/defaultmea` existed on the old service and now return
**404**. Code using them is targeting the dead API.

---

## Socket.IO

### Subscribe

```
emit "start" {"id_intan": "<_id>", "mea_index": 0, "channel_index": [0,1,2,3]}
```

Unlike the old protocol (`emit "meaid", <0-3>`), you select an **arbitrary
subset of channels**. This is a genuine improvement — request only what you need.

### Receive

```
on "data"        -> flat array of floats
on "maintenance" -> maintenance state change
```

### Payload layout — channel-major

From the client's own `appendFlatData(e, t)`, where `t = numbersample` and
`s = n * t` for the n-th channel:

```
data[i * numbersample : (i + 1) * numbersample]  ==  channel_index[i]
```

So for `channel_index = [0,1,2,3]` and `numbersample = 1600`, the array is 6400
floats: `[ch0 × 1600, ch1 × 1600, ch2 × 1600, ch3 × 1600]`.

Reshape as `(n_channels, numbersample)` — **C order, channels first**.

### Payloads are JSON, not binary

Values arrive at full float64 print precision (e.g. `-1.792515516281128`),
confirming JSON text serialisation. The old protocol sent a binary `Float32Array`
buffer. This is significantly less efficient and is the cause of the throughput
limits below.

---

## Signal properties

| Property | Value | Source |
|---|---|---|
| Units | microvolts | client `amplitudeRangeUv` |
| Sample rate | **3750 Hz** | client constant `sn = 3750` |
| Hardware rate | 30 kHz | FinalSpark docs |
| Downsampling | wavelet transform, ÷8 | FinalSpark docs |
| Bandpass | 250–5000 Hz | FinalSpark docs |
| Packet duration | 1600 / 3750 = **0.4267 s** | derived |
| Client display window | 5 s (`sn * 5`) | client constant |
| Typical noise σ | 6–10 µV | measured |

---

## Throughput — measured, not specified

Delivery is variable and load-dependent. Across several runs:

| Channels | Payload (approx) | Observed interval |
|---|---|---|
| 4 | ~110 KB JSON | 0.6 – 5 s |
| 8 | ~240 KB JSON | ~1.5 s |
| 32 | ~970 KB JSON | up to ~20 s |

At 32 channels the payload approaches the advertised `maxPayload` of 1,000,000
bytes, which is the effective ceiling. Since one packet is only 0.427 s of
signal, coverage is intermittent at every channel count.

**Do not design anything that assumes gapless capture.**

---

## MEA geometries

Derived from `electrode_layout` coordinates.

### 4×8 (32 electrodes)

```
X (µm): 0,200,400,600 | 3000,3200,3400,3600 | 6000,6200,6400,6600 | 9000,9200,9400,9600
Y (µm): 0, 200, 400
```

Four organoid sites **3000 µm apart**, each an 8-electrode cluster spanning
600 × 400 µm on a 200 µm pitch. Matches the microscope images: four sites in a
row inside a microfluidic chamber, with trace fans converging on each.

### 60-electrode

```
X (µm): 0 … 1400 (8 values, 200 µm pitch)
Y (µm): 0 … 1400, plus one electrode at 1800
```

60 entries = 8×8 grid minus 4 corners, plus an internal reference at y=1800.
Consistent with the commercial `60MEA200/30iR` part family (200 µm spacing,
30 µm electrodes, internal reference).

---

## Global electrode indexing (NeuroPlatform-wide)

The platform indexes electrodes 0–127 across four MEAs:

```
MEA  = index // 32
site = (index % 32) // 8
```

The live service uses **per-controller, per-MEA** `channel_index` instead, so the
two schemes do not directly coincide. Do not mix them.

---

## Attribution

> Data source: FinalSpark NeuroPlatform (https://finalspark.com)

FinalSpark's documentation for the previous service stated the code and data were
usable by non-NeuroPlatform users, asking only that FinalSpark be credited as the
source. No equivalent statement has been published for `livenp`. Credit them, and
ask before building anything load-bearing on this endpoint.
