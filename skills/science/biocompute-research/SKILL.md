---
name: biocompute-research
description: >
  Run rigorous biological-computing research using the BioCompute subsystem:
  formulate research questions, design pre-registered experiments with controls,
  acquire neural recordings from a simulator or live organoid MEAs, process
  signals, detect spike events, train and benchmark decoders against conventional
  baselines, run statistically valid evaluation, and generate reproducible
  reports. Use when the user wants to design or run a neural experiment, decode
  neural activity, benchmark biological against conventional computing, analyse
  MEA recordings, or produce a publication-grade experimental report. Also use
  when the user makes claims about biological computing that need evidence.
version: 1.0.0
author: Tchuekam Agent
license: MIT
metadata:
  tchuekam:
    tags: [research, neuroscience, biocomputing, experiments, benchmarking, statistics, reproducibility]
    related_skills: [finalspark-livemea, pubmed-database, literature-search-arxiv, uv]
prerequisites:
  commands: [python]
---

# BioCompute Research

Methodology skill for biological-computing research. The subsystem lives at
`biocompute/`; the docs are in `docs/biocompute/`.

## Prerequisites

```bash
pip install -e '.[biocompute]'
```

## The rule that governs everything

**Never let an inference become a result.** Label every statement:

| Level | Requires |
|---|---|
| `FACT` | in source code, documentation, or a published paper |
| `MEASUREMENT` | we ran it and recorded it, with parameters and provenance |
| `INFERENCE` | follows logically, but was not itself observed |
| `HYPOTHESIS` | testable, not yet tested |
| `SPECULATION` | plausible, unsupported — never in a conclusion |

If asked to summarise findings, carry these labels into the summary. Do not drop them
because they make the writing heavier.

## Hard constraints

- **Read-only.** Nothing here stimulates biological tissue. `stimulate()` raises
  `PermissionError` at the base class. Do not attempt to add stimulation.
- **Never bypass** authentication, authorisation, booking, or rate limits on any platform.
- **Never manufacture labels.** If the setup did not genuinely know the condition, the
  experiment is descriptive. Say so.
- **Never invent energy or cost numbers.** Unmeasured stays `None`.
- **Report negative results as negative.** A null result is a result.
- Live services are shared infrastructure — request the fewest channels needed, keep
  recordings small, do not poll aggressively.

## The 14-step research loop

1. **Formulate the question.** Narrow enough to answer with the data you can actually get.
2. **Search the literature** — use `pubmed-database`, `literature-search-arxiv`.
3. **State H1 and H0**, plus `evidence_for` and `evidence_against`, *before* running anything.
4. **Design the experiment** as an `ExperimentSpec`.
5. **Choose controls.** At minimum a null/negative control and a permutation test. Name
   every known confound and the control addressing it.
6. **Validate on the simulator first.** If the pipeline cannot recover a signal you know is
   present, it will not find a real one.
7. **Acquire data** within authorised scope.
8. **Process** through `default_pipeline()`; never hand-roll preprocessing.
9. **Decode** with `ExperimentRunner`.
10. **Benchmark** against conventional baselines on the identical task.
11. **Test statistically** — selection-corrected permutation test, always.
12. **State limitations** explicitly, including what the result does *not* show.
13. **Generate a reproducible report** with a manifest.
14. **Propose the next experiment.**

## Commands

```bash
python -m biocompute.cli providers --probe
python -m biocompute.cli analyze --provider simulator --segments 4 --pretty --plots
python -m biocompute.cli record --provider finalspark --channels 0-7 --segments 6 --save
python -m biocompute.cli experiment e1 --permutations 100 --report      # pipeline validation
python -m biocompute.cli experiment e2 --channels 8-15 --segments 14 --normalize --report
python -m biocompute.cli benchmark --permutations 60 --report
```

## Statistical rules you must not break

**Chance is the majority-class rate, not 1/K.** With imbalanced labels `1/n_classes`
understates chance and inflates every margin.

**Always permutation-test.** Small n produces above-chance cross-validated accuracy by luck
routinely. `p = (1 + #{null ≥ observed}) / (1 + n_permutations)`; p is never 0, and the
floor is `1/(1+n_permutations)` — with 60 permutations you cannot report below p ≈ 0.016.

**Correct for model selection.** If you try K models and report the best, use
`permutation_test_best_of()`. Testing the winner against a single-model null is a
winner's-curse error. Measured in this codebase on label-free data: individual models
averaged 0.49 accuracy, best-of-5 averaged **0.537**. That bias produced a **false positive
at p = 0.030** on a null dataset until it was corrected.

**Decodability ≠ mechanism.** Above-chance accuracy shows labels are decodable. It does not
identify *which* property carries the information. Run the controls before attributing a
mechanism.

## Interpreting neural data

- Events are **threshold crossings**, not sorted spikes. During bursts, several spikes
  merge into one event. Never report event counts as spike counts.
- <30 µV is likely noise; 200–1000 µV is likely artifact.
- A quiet channel may mean no tissue contact or a dead culture, not a bug.
- On the FinalSpark public feed, content above 1875 Hz is aliased (30 kHz band-limited
  250–5000 Hz, then downsampled ÷8 to 3750 Hz). Waveform-based spike sorting is not
  trustworthy on that feed.
- Segments are **not contiguous** on gappy providers. Never compute an interval across a
  segment boundary.

## Claims to refuse

If asked to state any of these without measured evidence, decline and explain what would be
needed:

- "we proved biological computation"
- "we proved organoid learning"
- "neurons are computing"
- "biological compute is N% cheaper" — energy and cost are `None` until measured
- any clinical, diagnostic, or consciousness claim

The "0.11% of training cost" figure is a **HYPOTHESIS**, not a result.

## What the current results actually support

**MEASUREMENT.** The pipeline captures and analyses live neural electrical activity from
human brain organoids, and recovers known synthetic signal while correctly rejecting a null
dataset (E1: real p = 0.0099, null control p = 0.1111).

**MEASUREMENT.** Electrodes on a live organoid MEA are distinguishable above chance after
amplitude normalisation (E2: 0.394 vs 0.125 chance, p = 0.025), so they differ in signal
structure and not only in gain.

**NOT ESTABLISHED.** Computation, learning, information processing, any energy or cost
advantage, or anything about biological versus conventional performance.

## Reference

- `docs/biocompute/ARCHITECTURE.md` — layers and design decisions
- `docs/biocompute/EXPERIMENTS.md` — E1/E2 with measured results
- `docs/biocompute/NEURAL_DATA.md` — schema, units, aliasing, label rules
- `docs/biocompute/BENCHMARKING.md` — statistical rules and the selection-bias measurement
- `docs/biocompute/SAFETY.md` — read-only enforcement, future stimulation architecture
- `docs/biocompute/PROVIDERS.md` — capabilities and how to add a backend

*Data source for live recordings: FinalSpark NeuroPlatform (https://finalspark.com)*
