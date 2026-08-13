"""Scientific visualisations.

Every plot is labelled with units and, where relevant, the detection threshold that
produced it -- a raster with no stated threshold is not interpretable.

Uses the Agg backend so it works headless in CI and on servers.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _save(fig, out_dir: Path, name: str) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    _plt().close(fig)
    return str(path)


def plot_traces(ctx, out_dir: str | Path, segment: int = 0, name: str = "traces") -> str:
    """Stacked voltage traces for one segment, with detection thresholds drawn."""
    plt = _plt()
    out_dir = Path(out_dir)
    sig = ctx.signal[segment]
    n_ch = sig.shape[0]
    t = np.arange(sig.shape[1]) / ctx.sample_rate_hz

    fig, axes = plt.subplots(n_ch, 1, figsize=(11, max(2, 1.1 * n_ch)), sharex=True)
    if n_ch == 1:
        axes = [axes]
    for i, ax in enumerate(axes):
        ax.plot(t, sig[i], linewidth=0.5, color="#1f77b4")
        if ctx.noise_sigma is not None:
            thr = 6.0 * ctx.noise_sigma[i]
            ax.axhline(thr, color="crimson", linestyle="--", linewidth=0.6)
            ax.axhline(-thr, color="crimson", linestyle="--", linewidth=0.6)
        if ctx.spikes is not None:
            idx = ctx.spikes.indices.get((segment, i))
            if idx is not None and len(idx):
                ax.plot(idx / ctx.sample_rate_hz, sig[i][idx], "r.", markersize=4)
        ax.set_ylabel(f"ch{ctx.channels[i]}", fontsize=8)
        ax.tick_params(labelsize=7)
    axes[-1].set_xlabel("time (s)")
    fig.suptitle(
        f"Segment {segment} — voltage (µV). Dashed = 6σ threshold, red dots = events",
        fontsize=10,
    )
    return _save(fig, out_dir, name)


def plot_raster(ctx, out_dir: str | Path, name: str = "raster") -> str:
    """Event raster. Segments are drawn separated, because they are not contiguous."""
    plt = _plt()
    out_dir = Path(out_dir)
    trains = ctx.spikes
    fig, ax = plt.subplots(figsize=(11, max(2.5, 0.35 * len(ctx.channels) + 1.5)))

    seg_dur = trains.segment_duration_s
    for s in range(trains.n_segments):
        offset = s * seg_dur * 1.08  # visual gap marks the discontinuity
        for i, ch in enumerate(ctx.channels):
            times = trains.times_s(s, i)
            if len(times):
                ax.eventplot(times + offset, lineoffsets=i, linelengths=0.7,
                             colors="#1f77b4", linewidths=0.8)
        if s:
            ax.axvline(offset - seg_dur * 0.04, color="grey", linestyle=":", linewidth=0.8)

    ax.set_yticks(range(len(ctx.channels)))
    ax.set_yticklabels([f"ch{c}" for c in ctx.channels], fontsize=7)
    ax.set_xlabel("time (s), segments concatenated for display only — dotted = gap")
    ax.set_title("Event raster (6σ threshold crossings, not sorted spikes)", fontsize=10)
    return _save(fig, out_dir, name)


def plot_firing_rates(stats: dict, out_dir: str | Path, name: str = "firing_rates") -> str:
    plt = _plt()
    chans = list(stats.keys())
    rates = [stats[c]["firing_rate_per_min"] for c in chans]
    fig, ax = plt.subplots(figsize=(max(5, 0.5 * len(chans) + 2), 3.4))
    ax.bar(range(len(chans)), rates, color="#1f77b4")
    ax.set_xticks(range(len(chans)))
    ax.set_xticklabels([f"ch{c}" for c in chans], rotation=45, fontsize=7)
    ax.set_ylabel("events / minute")
    ax.set_title("Per-channel event rate", fontsize=10)
    return _save(fig, Path(out_dir), name)


def plot_isi_histogram(ctx, out_dir: str | Path, name: str = "isi") -> str:
    plt = _plt()
    from biocompute.neural.analysis import _isis_within_segments

    all_isis = [
        _isis_within_segments(ctx.spikes, i) for i in range(len(ctx.channels))
    ]
    pooled = np.concatenate([a for a in all_isis if len(a)]) if any(
        len(a) for a in all_isis
    ) else np.array([])

    fig, ax = plt.subplots(figsize=(6, 3.4))
    if len(pooled):
        ax.hist(pooled * 1000, bins=40, color="#1f77b4")
        ax.set_xlabel("inter-event interval (ms)")
    else:
        ax.text(0.5, 0.5, "no intervals (fewer than 2 events per segment)",
                ha="center", va="center", transform=ax.transAxes, fontsize=9)
        ax.set_xticks([])
    ax.set_ylabel("count")
    ax.set_title("ISI distribution (within segments only)", fontsize=10)
    return _save(fig, Path(out_dir), name)


def plot_correlation_matrix(pop: dict, channels: list[int], out_dir: str | Path,
                            name: str = "correlation") -> str:
    plt = _plt()
    corr = np.array(pop["correlation_matrix"])
    fig, ax = plt.subplots(figsize=(5.5, 4.6))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(channels)))
    ax.set_yticks(range(len(channels)))
    ax.set_xticklabels([f"{c}" for c in channels], fontsize=7, rotation=90)
    ax.set_yticklabels([f"{c}" for c in channels], fontsize=7)
    fig.colorbar(im, ax=ax, label="Pearson r")
    ax.set_title("Signal correlation (within segments, averaged)", fontsize=10)
    return _save(fig, Path(out_dir), name)


def plot_confusion(cm: list[list[int]], labels: list, out_dir: str | Path,
                   name: str = "confusion") -> str:
    plt = _plt()
    cm_arr = np.array(cm)
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    im = ax.imshow(cm_arr, cmap="Blues")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7, rotation=90)
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    thresh = cm_arr.max() / 2 if cm_arr.max() else 0
    for i in range(cm_arr.shape[0]):
        for j in range(cm_arr.shape[1]):
            ax.text(j, i, cm_arr[i, j], ha="center", va="center", fontsize=6,
                    color="white" if cm_arr[i, j] > thresh else "black")
    fig.colorbar(im, ax=ax)
    ax.set_title("Confusion matrix", fontsize=10)
    return _save(fig, Path(out_dir), name)


def plot_benchmark(engine, out_dir: str | Path, name: str = "benchmark") -> str:
    """Accuracy per model with the chance line drawn — the only honest way to show it."""
    plt = _plt()
    rows = [r for _, r in engine.rows]
    if not rows:
        raise ValueError("no benchmark rows to plot")

    names = [r.model for r in rows]
    accs = [r.accuracy_mean for r in rows]
    errs = [r.accuracy_std for r in rows]
    chance = rows[0].chance

    fig, ax = plt.subplots(figsize=(max(6, 1.4 * len(rows) + 2), 3.8))
    bars = ax.bar(range(len(rows)), accs, yerr=errs, capsize=3, color="#1f77b4")
    for i, r in enumerate(rows):
        if r.p_value is not None and r.p_value < 0.05:
            bars[i].set_color("#2ca02c")
    ax.axhline(chance, color="crimson", linestyle="--",
               label=f"chance (majority class) = {chance:.3f}")
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("cross-validated accuracy")
    ax.set_ylim(0, 1.02)
    ax.legend(fontsize=8)
    ax.set_title("Benchmark — green = p < 0.05 (permutation test)", fontsize=10)
    return _save(fig, Path(out_dir), name)
