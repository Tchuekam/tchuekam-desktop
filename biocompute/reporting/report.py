"""Reproducible experiment reports.

A report never upgrades the evidence level of a statement. If the runner produced
a negative result, the report says so in the heading. There is no code path here
that turns "not significant" into "trending towards".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from biocompute.benchmarks.engine import BenchmarkEngine
from biocompute.core.provenance import ExperimentManifest
from biocompute.experiments.spec import ExperimentResult
from biocompute.neural.analysis import human_summary


def _verdict(result: ExperimentResult) -> str:
    supported = result.hypothesis_supported
    if supported is None:
        return "UNDETERMINED — descriptive characterisation only, no hypothesis tested"
    if supported:
        return "HYPOTHESIS SUPPORTED (with the stated confounds still open)"
    return "NULL HYPOTHESIS NOT REJECTED — negative result"


def generate_markdown(
    result: ExperimentResult,
    benchmark: BenchmarkEngine | None = None,
    figures: list[str] | None = None,
) -> str:
    spec = result.spec
    rec = result.recording_summary.get("recording", {})
    manifest = None
    if result.manifest_path and Path(result.manifest_path).exists():
        manifest = ExperimentManifest.load(result.manifest_path)

    L: list[str] = [
        f"# {spec.name}",
        "",
        f"*Generated {datetime.now(timezone.utc).isoformat()}*",
        "",
        f"## Verdict: {_verdict(result)}",
        "",
        "## 1. Pre-registered question",
        "",
        f"**Research question.** {spec.research_question}",
        "",
        f"**Hypothesis (H1).** {spec.hypothesis}",
        "",
        f"**Null hypothesis (H0).** {spec.null_hypothesis}",
        "",
        f"**Task.** {spec.task}",
        "",
        f"**Evidence FOR would be:** {spec.evidence_for}",
        "",
        f"**Evidence AGAINST would be:** {spec.evidence_against}",
        "",
        "## 2. Method",
        "",
        f"- **Provider:** `{spec.provider}`",
        f"- **Label source:** {spec.label_source.description} "
        f"(ground truth: {spec.label_source.is_ground_truth})",
        f"- **Independent variables:** {', '.join(spec.independent_variables)}",
        f"- **Dependent variables:** {', '.join(spec.dependent_variables)}",
        f"- **Significance level:** α = {spec.alpha}",
        "",
        "**Controls:**",
        "",
    ]
    L += [f"- {c}" for c in spec.controls]
    L += ["", "**Protocol:**", ""]
    L += [f"{i}. {p}" for i, p in enumerate(spec.protocol, 1)]

    if spec.label_source.caveats:
        L += ["", "**Label caveats:**", ""] + [f"- {c}" for c in spec.label_source.caveats]

    # ---- data
    L += ["", "## 3. Data", ""]
    if rec:
        biological = (rec.get("provider_metadata") or {}).get("biological")
        L += [
            f"- **Source:** `{rec.get('provider')}` / `{rec.get('session_id')}`",
            f"- **Biological sample:** {biological}",
            f"- **Sample rate:** {rec.get('sample_rate_hz')} Hz",
            f"- **Segments:** {rec.get('n_segments')} × "
            f"{rec.get('segment_duration_s')} s = {rec.get('duration_s')} s of signal",
            f"- **Contiguous:** {rec.get('contiguous')}",
            f"- **Channels:** {rec.get('channels')}",
            f"- **Data hash:** `{rec.get('data_hash')}`",
        ]
        if rec.get("duty_cycle") is not None:
            L.append(f"- **Duty cycle:** {rec['duty_cycle'] * 100:.1f}% of wall-clock span")

    L += ["", "### Signal statistics", "", "```", human_summary(result.recording_summary), "```"]

    # ---- results
    L += ["", "## 4. Results", ""]
    if result.model_results:
        L += [
            "| model | accuracy | ± | chance | margin | p |",
            "|---|---|---|---|---|---|",
        ]
        for name, r in sorted(
            result.model_results.items(), key=lambda kv: -kv[1]["accuracy_mean"]
        ):
            p = r.get("permutation_p_value")
            L.append(
                f"| `{name}` | {r['accuracy_mean']:.3f} | {r['accuracy_std']:.3f} | "
                f"{r['chance_accuracy']:.3f} | "
                f"{r['accuracy_mean'] - r['chance_accuracy']:+.3f} | "
                f"{f'{p:.4f}' if p is not None else '—'} |"
            )
    else:
        L.append("No decoding was performed (descriptive experiment).")

    # ---- benchmark
    if benchmark and benchmark.rows:
        L += ["", "## 5. Benchmark", "", "```", benchmark.render_table(), "```"]

    # ---- conclusions
    L += ["", "## 6. Conclusions", "", "*Each statement carries its evidence level.*", ""]
    for s in result.conclusion:
        L.append(f"- **[{s.level.value}]** {s.text}")
        if s.support:
            L.append(f"  - *support:* {s.support}")

    # ---- confounds and limitations
    if spec.known_confounds:
        L += ["", "## 7. Known confounds (open)", ""] + [f"- {c}" for c in spec.known_confounds]
    if result.limitations:
        L += ["", "## 8. Limitations", ""] + [f"- {x}" for x in result.limitations]

    # ---- reproducibility
    L += ["", "## 9. Reproducibility", ""]
    if manifest:
        env = manifest.environment or {}
        L += [
            f"- **Manifest:** `{result.manifest_path}`",
            f"- **Fingerprint:** `{manifest.fingerprint()}`",
            f"- **Git commit:** `{manifest.git_commit or 'unknown'}`"
            + ("  ⚠️ working tree dirty" if manifest.git_dirty else ""),
            f"- **BioCompute version:** {manifest.biocompute_version}",
            f"- **Python:** {env.get('python')} on {env.get('platform')}",
            f"- **Seeds:** {manifest.random_seeds}",
            f"- **Dataset hash:** `{manifest.dataset_hash}`",
        ]
        pkgs = env.get("packages") or {}
        if pkgs:
            L.append(
                "- **Packages:** "
                + ", ".join(f"{k}={v}" for k, v in pkgs.items() if v)
            )
    else:
        L.append("- ⚠️ No manifest was written; this run is not reproducible.")

    if figures:
        L += ["", "## 10. Figures", ""] + [f"![{Path(f).stem}]({f})" for f in figures]

    if result.next_experiment:
        L += ["", "## Next experiment", "", result.next_experiment]

    L += [
        "",
        "---",
        "",
        "*Generated by TchueKAM BioCompute. Statements are labelled FACT / MEASUREMENT "
        "/ INFERENCE / HYPOTHESIS / SPECULATION and are never promoted between levels.*",
    ]
    if rec.get("provider") == "finalspark":
        L += ["", "*Data source: FinalSpark NeuroPlatform (https://finalspark.com)*"]
    return "\n".join(L)


def save_report(
    result: ExperimentResult,
    output_dir: str | Path,
    benchmark: BenchmarkEngine | None = None,
    figures: list[str] | None = None,
) -> dict[str, str]:
    """Write report.md + result.json. Returns the paths."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = result.spec.name

    md_path = out / f"{stem}.report.md"
    md_path.write_text(generate_markdown(result, benchmark, figures), encoding="utf-8")

    json_path = out / f"{stem}.result.json"
    payload = result.to_dict()
    if benchmark:
        payload["benchmark"] = benchmark.to_dict()
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    return {"markdown": str(md_path), "json": str(json_path)}
