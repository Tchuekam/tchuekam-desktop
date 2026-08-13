"""Spike/event statistics and population measures.

Everything here is computed WITHIN segments and then aggregated, because for gappy
providers consecutive segments are separated by unknown wall-clock gaps. An ISI
computed across a seam would be meaningless, so cross-segment intervals are never
formed.

Output is a plain dict so it serialises straight to JSON alongside the provenance
manifest.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from biocompute.core.schema import Recording
from biocompute.neural.pipeline import PipelineContext, SpikeTrains


def _isis_within_segments(trains: SpikeTrains, ch_idx: int) -> np.ndarray:
    """Inter-event intervals in seconds, never crossing a segment boundary."""
    out: list[np.ndarray] = []
    for s in range(trains.n_segments):
        idx = trains.indices.get((s, ch_idx))
        if idx is not None and len(idx) > 1:
            out.append(np.diff(idx) / trains.sample_rate_hz)
    return np.concatenate(out) if out else np.array([])


def detect_bursts(
    event_times_s: np.ndarray,
    max_isi_s: float = 0.1,
    min_events: int = 3,
) -> list[tuple[float, float, int]]:
    """Group events into bursts by a maximum-ISI rule.

    Simple and interpretable (the classic max-ISI method). Returns
    (start_s, end_s, n_events) per burst. Not adaptive -- state the parameters
    whenever burst counts are reported.
    """
    if len(event_times_s) < min_events:
        return []
    bursts, start, count = [], event_times_s[0], 1
    for prev, cur in zip(event_times_s[:-1], event_times_s[1:]):
        if cur - prev <= max_isi_s:
            count += 1
        else:
            if count >= min_events:
                bursts.append((float(start), float(prev), int(count)))
            start, count = cur, 1
    if count >= min_events:
        bursts.append((float(start), float(event_times_s[-1]), int(count)))
    return bursts


def channel_statistics(ctx: PipelineContext, burst_max_isi_s: float = 0.1,
                       burst_min_events: int = 3) -> dict[str, Any]:
    """Per-channel event statistics."""
    trains = ctx.spikes
    if trains is None:
        raise RuntimeError("channel_statistics requires a pipeline with DetectSpikes")

    dur_total = trains.n_segments * trains.segment_duration_s
    out: dict[str, Any] = {}

    for i, ch in enumerate(ctx.channels):
        total = trains.channel_total(i)
        isis = _isis_within_segments(trains, i)

        amps = [trains.amplitudes[(s, i)] for s in range(trains.n_segments)
                if (s, i) in trains.amplitudes]
        amps_arr = np.concatenate(amps) if amps else np.array([])

        bursts_all: list[tuple[float, float, int]] = []
        for s in range(trains.n_segments):
            bursts_all.extend(
                detect_bursts(trains.times_s(s, i), burst_max_isi_s, burst_min_events)
            )

        sigma = float(ctx.noise_sigma[i]) if ctx.noise_sigma is not None else None
        peak = float(np.abs(ctx.signal[:, i, :]).max())

        out[str(ch)] = {
            "event_count": total,
            "firing_rate_hz": round(total / dur_total, 4) if dur_total else 0.0,
            "firing_rate_per_min": round(total / dur_total * 60, 2) if dur_total else 0.0,
            "isi_mean_s": round(float(isis.mean()), 6) if len(isis) else None,
            "isi_median_s": round(float(np.median(isis)), 6) if len(isis) else None,
            "isi_cv": (
                round(float(isis.std() / isis.mean()), 4)
                if len(isis) and isis.mean() > 0 else None
            ),
            "n_isi_samples": int(len(isis)),
            "noise_sigma_uv": round(sigma, 4) if sigma is not None else None,
            "peak_abs_uv": round(peak, 3),
            "snr_peak_over_sigma": round(peak / sigma, 3) if sigma else None,
            "event_amplitude_mean_uv": (
                round(float(np.abs(amps_arr).mean()), 3) if len(amps_arr) else None
            ),
            "n_bursts": len(bursts_all),
            "burst_event_fraction": (
                round(sum(b[2] for b in bursts_all) / total, 4) if total else 0.0
            ),
            "active": total > 0,
        }
    return out


def population_statistics(ctx: PipelineContext) -> dict[str, Any]:
    """Cross-channel measures: participation, correlation, synchrony."""
    trains = ctx.spikes
    if trains is None:
        raise RuntimeError("population_statistics requires a pipeline with DetectSpikes")

    n_ch = len(ctx.channels)
    totals = np.array([trains.channel_total(i) for i in range(n_ch)], dtype=float)
    dur_total = trains.n_segments * trains.segment_duration_s

    # Signal correlation, computed per segment then averaged (never across seams).
    # Cross-channel measures are undefined for a single-channel recording (which is
    # what the channel-identity reshape produces), so they stay None rather than
    # being faked with a 1x1 self-correlation of 1.0.
    if n_ch > 1:
        corrs = [
            np.corrcoef(ctx.signal[s])
            for s in range(trains.n_segments)
            if np.all(ctx.signal[s].std(axis=1) > 0)
        ]
        corr = np.mean(corrs, axis=0) if corrs else np.eye(n_ch)
        off = corr[~np.eye(n_ch, dtype=bool)]
    else:
        corr = np.ones((1, 1))
        off = None

    # Event-count correlation across segments, if there are enough segments.
    count_matrix = np.array(
        [[trains.count(s, i) for i in range(n_ch)] for s in range(trains.n_segments)],
        dtype=float,
    )
    count_corr = None
    if n_ch > 1 and trains.n_segments >= 3 and np.all(count_matrix.std(axis=0) > 0):
        count_corr = float(
            np.mean(np.corrcoef(count_matrix.T)[~np.eye(n_ch, dtype=bool)])
        )

    return {
        "n_channels": n_ch,
        "n_active_channels": int((totals > 0).sum()),
        "active_fraction": round(float((totals > 0).mean()), 4),
        "total_events": int(totals.sum()),
        "population_rate_hz": round(float(totals.sum() / dur_total), 4) if dur_total else 0.0,
        "event_count_gini": round(_gini(totals), 4),
        "signal_correlation_mean": round(float(off.mean()), 4) if off is not None else None,
        "signal_correlation_max": round(float(off.max()), 4) if off is not None else None,
        "event_count_correlation_mean": (
            round(count_corr, 4) if count_corr is not None else None
        ),
        "correlation_matrix": np.round(corr, 4).tolist(),
        "notes": [
            "correlations computed within segments and averaged; never across gaps",
            "event_count_gini: 0 = events spread evenly across channels, 1 = all on one",
        ],
    }


def _gini(x: np.ndarray) -> float:
    """Inequality of event distribution across channels."""
    if x.sum() == 0:
        return 0.0
    xs = np.sort(x)
    n = len(xs)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(xs) / (n * xs.sum()))


def summarize(ctx: PipelineContext, recording: Recording) -> dict[str, Any]:
    """Full machine-readable analysis result with provenance attached."""
    return {
        "recording": recording.metadata_dict(),
        "channels": channel_statistics(ctx),
        "population": population_statistics(ctx),
        "warnings": ctx.warnings,
        "interpretation_notes": [
            "Events are threshold crossings, NOT sorted spikes. During bursts several "
            "true spikes merge into one event.",
            "Amplitudes below ~30 uV are likely noise; 200-1000 uV is likely artifact "
            "(FinalSpark guidance).",
            "A quiet channel may mean no tissue contact or a dead culture, not a bug.",
        ],
    }


def human_summary(result: dict[str, Any]) -> str:
    """Readable rendering of `summarize()` output."""
    rec = result["recording"]
    pop = result["population"]
    lines = [
        "NEURAL RECORDING SUMMARY",
        "=" * 60,
        f"provider      : {rec['provider']}",
        f"session       : {rec['session_id']}",
        f"recorded      : {rec['timestamp']}",
        f"sample rate   : {rec['sample_rate_hz']:.0f} Hz",
        f"segments      : {rec['n_segments']} x {rec['segment_duration_s']:.3f} s "
        f"= {rec['duration_s']:.3f} s of signal",
        f"contiguous    : {rec['contiguous']}"
        + ("" if rec["contiguous"] else "  (gaps between segments -- not continuous)"),
    ]
    if rec.get("duty_cycle") is not None:
        lines.append(f"duty cycle    : {rec['duty_cycle'] * 100:.1f}% of wall-clock span")
    lines += [
        f"channels      : {rec['n_channels']}  {rec['channels']}",
        "",
        f"ACTIVITY: {pop['total_events']} events, "
        f"{pop['n_active_channels']}/{pop['n_channels']} channels active, "
        f"population rate {pop['population_rate_hz']:.3f} Hz",
        (
            f"mean pairwise signal correlation: {pop['signal_correlation_mean']:.3f}"
            if pop["signal_correlation_mean"] is not None
            else "mean pairwise signal correlation: n/a (single-channel recording)"
        ),
        "",
        f"{'ch':>5} {'events':>7} {'rate/min':>9} {'sigma_uV':>9} {'peak_uV':>8} "
        f"{'SNR':>6} {'bursts':>7}",
        "-" * 60,
    ]
    for ch, s in result["channels"].items():
        lines.append(
            f"{ch:>5} {s['event_count']:>7} {s['firing_rate_per_min']:>9.1f} "
            f"{(s['noise_sigma_uv'] or 0):>9.2f} {s['peak_abs_uv']:>8.1f} "
            f"{(s['snr_peak_over_sigma'] or 0):>6.1f} {s['n_bursts']:>7}"
        )
    if result.get("warnings"):
        lines += ["", "WARNINGS:"] + [f"  - {w}" for w in result["warnings"]]
    lines += ["", "NOTES:"] + [f"  - {n}" for n in result["interpretation_notes"]]
    return "\n".join(lines)
