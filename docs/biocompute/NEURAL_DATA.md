# BioCompute — Neural Data Standard

## `Recording`

The provider-neutral representation. One schema, every backend.

| Field | Meaning |
|---|---|
| `experiment_id` · `provider` · `session_id` · `timestamp` | identity |
| `sample_rate_hz` · `units` | scale. Units are `microvolts` unless normalised |
| `channels` | channel indices, in the order they appear in `data` |
| `data` | float32 `(n_segments, n_channels, n_samples)` |
| `segment_timestamps` | one wall-clock timestamp per segment |
| `contiguous` | **False if gaps exist between segments** |
| `channel_layout` | electrode positions in micrometres |
| `stimulus_metadata` | labels + their source, or `None` |
| `processing_parameters` | ordered log of every applied step and its effective params |
| `raw_data_reference` · `processed_data_reference` | file paths |
| `provider_metadata` | **provider-specific fields are preserved here, never discarded** |

Derived: `duration_s` (signal only, gaps excluded), `wall_clock_span_s`, `duty_cycle`,
`data_hash()`.

## Why segments, not one continuous array

FinalSpark's public feed delivers 0.427 s packets separated by variable gaps of
0.6–20 s. Concatenating them would fabricate continuity that does not exist. Every
inter-spike interval, burst boundary and correlation computed across a seam would be
wrong, and nothing downstream would be able to tell.

So:

- `data` keeps segments separate.
- `contiguous=False` marks the gaps.
- `assert_contiguous(op)` raises for any operation that requires continuity.
- Analysis computes ISIs **within** segments and pools them; it never forms a
  cross-segment interval.
- The raster plot draws visible gaps between segments.

`duty_cycle` tells you how much of the wall clock the signal actually covers. On the
public feed at 32 channels this has been measured as low as ~2%.

## FinalSpark signal properties

| Property | Value | Source |
|---|---|---|
| Units | microvolts | client constant |
| Sample rate | **3750 Hz** | client constant `sn = 3750` |
| Hardware rate | 30 kHz | FinalSpark docs |
| Downsampling | wavelet, ÷8 | FinalSpark docs |
| Upstream bandpass | 250–5000 Hz | FinalSpark docs |
| Segment | 1600 samples = 0.4267 s | `/sample` endpoint |
| Typical noise σ | 6–10 µV | measured |

### The aliasing caveat

The signal was band-limited to **250–5000 Hz** *before* being downsampled to 3750 Hz.
Nyquist at 3750 Hz is **1875 Hz**, so content between 1875 and 5000 Hz is aliased and
cannot be recovered.

Consequence: **spike waveform shape on this feed is degraded.** Spike energy extends well
above 1875 Hz. Event *detection* remains usable; waveform-based spike *sorting* on this
feed is not trustworthy.

The `Validate` step emits this warning automatically whenever
`provider_metadata["upstream_bandpass_hz"]` exceeds Nyquist.

## Events are not spikes

An "event" is a threshold crossing at 6σ with a 3 ms refractory window — the same
definition FinalSpark uses. It is **not** spike sorting:

- During bursts, several true spikes merge into one event.
- At 3750 Hz, 3 ms is only ~11 samples.
- No neuron identity is resolved.

Report counts as **events**. Never call them spikes.

## Amplitude interpretation

From FinalSpark's own documentation:

| Amplitude | Reading |
|---|---|
| < 30 µV | likely noise |
| ~50–150 µV | plausible biological spike (typically ≤100 µV, ~1 ms) |
| 200–1000 µV | almost certainly stimulation or electrical artifact |

A perfectly regular signal with constant amplitude and frequency is noise, not an
organoid — commonly an electrode the spheroid does not fully cover.

## Noise estimation

Default is **MAD**: `σ̂ = median(|x|) / 0.6745` (Quiroga et al. 2004), which is robust
against the very spikes being detected. `std` is available but inflates in the presence of
activity — measured here at >1.5× the MAD estimate on spiky data, which would silently
*raise* the detection threshold and *lose* events exactly when activity is highest.

## Labels

`stimulus_metadata` must record **where labels came from**, and `LabelSource` refuses to
proceed when they are not valid for supervised learning.

On the read-only public feed **no stimulus is ever applied**, so no stimulus label exists.
The only genuinely known labels are structural — e.g. which electrode a segment came from.
Inventing a stimulus label from an assumption is fabrication and the runner will reject it.

## Storage

`DatasetStore` always writes the HDF5 array **and** its manifest together. A recording
without provenance is not a dataset.

```
biocompute_data/
├── <dataset_id>.h5              data + embedded metadata JSON
├── <dataset_id>.manifest.json   git commit, env, seeds, hashes
└── index.json
```
