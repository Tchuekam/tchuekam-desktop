#!/usr/bin/env python3
"""BioCompute CLI -- drives the full pipeline for any provider.

    python -m biocompute.cli providers
    python -m biocompute.cli record --provider simulator --segments 4 --save
    python -m biocompute.cli analyze --provider finalspark --channels 10-15 --segments 6
    python -m biocompute.cli experiment e1 --report
    python -m biocompute.cli experiment e2 --channels 8-15 --segments 12 --report
    python -m biocompute.cli benchmark --report

`--provider finalspark` contacts the live public service and is READ-ONLY.
Everything else runs offline against the simulator.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from biocompute.core.registry import available, get_provider
from biocompute.core.schema import RecordRequest
from biocompute.experiments.exp001_visual_classification import run_experiment_001



def parse_channels(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return sorted(out)


def _emit(obj, pretty: bool):
    print(json.dumps(obj, indent=2, default=str) if not pretty else obj)


# ------------------------------------------------------------------ commands


def cmd_providers(args):
    rows = []
    for name in available():
        try:
            p = get_provider(name)
            info = p.describe()
            if args.probe:
                conn = p.connect()
                info["reachable"] = conn.reachable
                info["detail"] = conn.detail
            rows.append(info)
        except Exception as e:  # noqa: BLE001
            rows.append({"name": name, "error": f"{type(e).__name__}: {e}"})
    print(json.dumps({"providers": rows}, indent=2, default=str))


def _record(args):
    kwargs = {}
    if args.provider == "simulator":
        kwargs = {"n_channels": args.sim_channels, "seed": args.seed}
    provider = get_provider(args.provider, **kwargs)
    conn = provider.connect()
    if not conn.reachable:
        print(f"provider '{args.provider}' unreachable: {conn.detail}", file=sys.stderr)
        sys.exit(2)
    return provider, provider.record(
        RecordRequest(
            device_id=args.device,
            channels=parse_channels(args.channels),
            n_segments=args.segments,
            timeout_s=args.timeout,
            experiment_id=args.experiment_id,
        )
    )


def cmd_record(args):
    _, rec = _record(args)
    out = {"recording": rec.metadata_dict()}
    if args.save:
        from biocompute.datasets.store import DatasetStore

        store = DatasetStore(args.data_dir)
        out["saved"] = store.save(rec)
        store.write_index()
    print(json.dumps(out, indent=2, default=str))


def cmd_analyze(args):
    from biocompute.neural.analysis import human_summary, summarize
    from biocompute.neural.pipeline import default_pipeline

    _, rec = _record(args)
    ctx = default_pipeline(threshold_sigma=args.threshold_sigma).run(rec)
    result = summarize(ctx, rec)

    if args.plots:
        from biocompute.reporting import plots

        d = Path(args.out_dir) / "figures"
        figs = [
            plots.plot_traces(ctx, d),
            plots.plot_raster(ctx, d),
            plots.plot_firing_rates(result["channels"], d),
            plots.plot_isi_histogram(ctx, d),
            plots.plot_correlation_matrix(result["population"], ctx.channels, d),
        ]
        result["figures"] = figs

    if args.pretty:
        print(human_summary(result))
        if args.plots:
            print("\nfigures: " + ", ".join(result["figures"]))
    else:
        print(json.dumps(result, indent=2, default=str))


def cmd_experiment(args):
    from biocompute.experiments.library import (
        channel_identity_dataset,
        e1_simulator_stimulus_decoding,
        e2_channel_identity_decoding,
    )
    from biocompute.experiments.runner import ExperimentRunner
    from biocompute.models.baselines import DEFAULT_BASELINES
    from biocompute.models.reservoir import ReservoirModel
    from biocompute.neural.pipeline import default_pipeline
    from biocompute.reporting.report import save_report

    models = [*DEFAULT_BASELINES, lambda: ReservoirModel(n_units=120, seed=args.seed)]
    runner = ExperimentRunner(output_dir=args.out_dir)

    if args.which == "e1":
        from biocompute.providers.simulator.adapter import SimulatorProvider

        spec = e1_simulator_stimulus_decoding(seed=args.seed)
        sim = SimulatorProvider(n_channels=args.sim_channels, seed=args.seed)
        rec = sim.record_labeled(
            n_classes=args.classes, trials_per_class=args.trials, seed=args.seed
        )
        labels = np.array(rec.stimulus_metadata["labels"])
        result = runner.run(spec, rec, labels, models,
                            pipeline=default_pipeline(),
                            n_permutations=args.permutations,
                            provider_config=sim.config())

        # Negative control: same generator with the stimulus effect removed.
        null_rec = sim.record_labeled(
            n_classes=args.classes, trials_per_class=args.trials,
            seed=args.seed + 1, response_gain=0.0,
        )
        null_spec = e1_simulator_stimulus_decoding(seed=args.seed)
        null_spec.name = "E1-NULL-control"
        null_result = runner.run(
            null_spec, null_rec, np.array(null_rec.stimulus_metadata["labels"]),
            models, pipeline=default_pipeline(),
            n_permutations=args.permutations, provider_config=sim.config(),
        )
        print(json.dumps({
            "real": {"accuracy": result.primary_metric, "chance": result.chance_level,
                     "p": result.p_value, "supported": result.hypothesis_supported},
            "null_control": {"accuracy": null_result.primary_metric,
                             "chance": null_result.chance_level,
                             "p": null_result.p_value,
                             "supported": null_result.hypothesis_supported},
            "control_passed": null_result.hypothesis_supported is False,
        }, indent=2, default=str))
    else:
        spec = e2_channel_identity_decoding(seed=args.seed)
        args.provider = "finalspark"
        _, raw = _record(args)
        rec, labels = channel_identity_dataset(raw)
        result = runner.run(
            spec, rec, labels, models,
            pipeline=default_pipeline(normalize_amplitude=args.normalize),
            n_permutations=args.permutations,
        )
        print(json.dumps({
            "amplitude_control_applied": args.normalize,
            "condition": "CONTROL (unit-sigma normalised)" if args.normalize
                         else "UNCONTROLLED (raw amplitude)",
            "accuracy": result.primary_metric,
            "chance": result.chance_level,
            "p": result.p_value,
            "supported": result.hypothesis_supported,
        }, indent=2, default=str))

    if args.report:
        paths = save_report(result, args.out_dir)
        print(json.dumps({"report": paths}, indent=2))
    for s in result.conclusion:
        print(f"  {s.render()}", file=sys.stderr)


def cmd_benchmark(args):
    from biocompute.benchmarks.engine import BenchmarkEngine, BenchmarkTask
    from biocompute.models.baselines import DEFAULT_BASELINES
    from biocompute.models.reservoir import ReservoirModel
    from biocompute.neural.pipeline import default_pipeline
    from biocompute.providers.simulator.adapter import SimulatorProvider

    sim = SimulatorProvider(n_channels=args.sim_channels, seed=args.seed)
    rec = sim.record_labeled(n_classes=args.classes, trials_per_class=args.trials,
                             seed=args.seed)
    ctx = default_pipeline().run(rec)
    task = BenchmarkTask(
        name="simulator-stimulus-classification",
        description="classify synthetic stimulus class from one trial",
        X=ctx.features,
        y=np.array(rec.stimulus_metadata["labels"]),
        seed=args.seed,
        data_provenance={"provider": "simulator", "biological": False,
                         "config": sim.config()},
    )
    engine = BenchmarkEngine(permutation_tests=True, n_permutations=args.permutations)
    engine.run(task, [*DEFAULT_BASELINES,
                      lambda: ReservoirModel(n_units=120, seed=args.seed)])
    print(engine.render_table())
    if args.report:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "benchmark.json").write_text(
            json.dumps(engine.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        from biocompute.reporting.plots import plot_benchmark

        print(f"\nfigure: {plot_benchmark(engine, out / 'figures')}")
        print(f"json  : {out / 'benchmark.json'}")


# --------------------------------------------------------------------- main


def main(argv=None):
    p = argparse.ArgumentParser(prog="biocompute", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, with_record=True):
        sp.add_argument("--provider", default="simulator", choices=available())
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--sim-channels", type=int, default=8)
        sp.add_argument("--out-dir", default="biocompute_runs")
        if with_record:
            sp.add_argument("--device", default=None)
            sp.add_argument("--channels", default=None, help="e.g. '0-7' or '0,3,5'")
            sp.add_argument("--segments", type=int, default=4)
            sp.add_argument("--timeout", type=float, default=180.0)
            sp.add_argument("--experiment-id", default="adhoc")

    sp = sub.add_parser("providers", help="list providers and capabilities")
    sp.add_argument("--probe", action="store_true", help="also test reachability")
    sp.set_defaults(func=cmd_providers)

    sp = sub.add_parser("record", help="acquire a recording")
    common(sp)
    sp.add_argument("--save", action="store_true")
    sp.add_argument("--data-dir", default="biocompute_data")
    sp.set_defaults(func=cmd_record)

    sp = sub.add_parser("analyze", help="record then run the full analysis pipeline")
    common(sp)
    sp.add_argument("--threshold-sigma", type=float, default=6.0)
    sp.add_argument("--plots", action="store_true")
    sp.add_argument("--pretty", action="store_true")
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("experiment", help="run a pre-registered experiment")
    sp.add_argument("which", choices=["e1", "e2"])
    common(sp)
    sp.add_argument("--classes", type=int, default=2)
    sp.add_argument("--trials", type=int, default=40)
    sp.add_argument("--permutations", type=int, default=200)
    sp.add_argument("--normalize", action="store_true",
                    help="E2 PRIMARY CONTROL: normalise each trace to unit noise "
                         "sigma, removing all per-channel gain information")
    sp.add_argument("--report", action="store_true")
    sp.set_defaults(func=cmd_experiment)

    sp = sub.add_parser("benchmark", help="matched-task model comparison")
    common(sp, with_record=False)
    sp.add_argument("--classes", type=int, default=2)
    sp.add_argument("--trials", type=int, default=40)
    sp.add_argument("--permutations", type=int, default=100)
    sp.add_argument("--report", action="store_true")
    sp.set_defaults(func=cmd_benchmark)

    sp = sub.add_parser("run-exp001", help="run Experiment #1: Visual Classification Benchmark")
    sp.add_argument("--samples", type=int, default=200)
    sp.add_argument("--classes", type=int, default=5)
    sp.add_argument("--seed", type=int, default=42)
    sp.set_defaults(func=lambda args: print(json.dumps(run_experiment_001(n_samples=args.samples, n_classes=args.classes, seed=args.seed), indent=2)))

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

