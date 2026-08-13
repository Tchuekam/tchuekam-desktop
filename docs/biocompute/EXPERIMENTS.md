# BioCompute — Experiments

## Pre-registration

An `ExperimentSpec` is declared **before** the experiment runs, and includes both
`evidence_for` and `evidence_against`. Writing the falsification criterion first is what
stops a result being reinterpreted afterwards to mean whatever it happened to show.

Every conclusion is a `Statement` carrying an `EvidenceLevel`:

| Level | Requires |
|---|---|
| `FACT` | stated in source, documentation, or a published paper |
| `MEASUREMENT` | we ran it and recorded it, with parameters and provenance |
| `INFERENCE` | follows from the above, but was not itself observed |
| `HYPOTHESIS` | testable, not yet tested |
| `SPECULATION` | plausible, unsupported — never appears in a conclusion |

Nothing is promoted between levels. There is no code path that turns
"not significant" into "trending".

## Labels cannot be manufactured

`LabelSource.validate()` raises unless `valid_for_supervised_learning` is True, and the
runner calls it before doing anything else.

On the read-only public feed **no stimulus is ever applied**, so no stimulus label exists.
Inventing one from an assumption ("activity rose, so a stimulus must have occurred") is
fabrication, and the framework refuses it.

---

## E1 — Simulator stimulus decoding (positive + null control)

**Question.** Can the pipeline recover a known stimulus class from synthetic activity?

**Purpose.** Validate the machinery. Success here says nothing about biology; it says the
software detects signal that is present *and does not invent signal that is absent*.

```bash
python -m biocompute.cli experiment e1 --classes 2 --trials 40 --permutations 100 --report
```

Two datasets from the same seeded generator:

- **real** — `response_gain=1.0`, stimulus-conditioned responses present
- **null** — `response_gain=0.0`, classes statistically identical

### Measured result (seed 0, 80 trials, 100 permutations)

| condition | best model | accuracy | chance | p | verdict |
|---|---|---|---|---|---|
| real | random_forest | **1.000** | 0.500 | **0.0099** | signal detected ✅ |
| null control | random_forest | 0.650 | 0.500 | **0.1111** | correctly not significant ✅ |

`control_passed: true`. The pipeline passes in both directions.

> The null control earned its place: with an uncorrected single-model permutation test it
> returned p = 0.030 — a false positive on data containing no signal. That is what exposed
> the selection-bias bug. See [BENCHMARKING.md](BENCHMARKING.md).

---

## E2 — FinalSpark channel identity

**Question.** Do individual electrodes on a live organoid MEA carry statistically
distinguishable signal?

**Why this experiment.** It is the first question we can legitimately ask of real organoid
data today. The provider is read-only, so there is no stimulus and no stimulus label. The
only label the setup genuinely knows is **which electrode a segment came from** — known
from the acquisition request itself, not inferred.

```bash
# uncontrolled
python -m biocompute.cli experiment e2 --channels 8-15 --segments 14 --permutations 100 --report
# PRIMARY CONTROL: removes all per-channel gain
python -m biocompute.cli experiment e2 --channels 8-15 --segments 14 --permutations 100 --normalize --report
```

### The confound and its control

Electrodes differ in noise amplitude. A decoder could separate them on **gain alone**,
which would be true but uninteresting.

`NormalizeAmplitude` divides every (segment, channel) trace by its own robust sigma, so
all traces have unit noise and no gain information survives. Anything still decodable
afterwards is signal **structure** — event rate, timing, shape.

> A column-wise z-score of the feature matrix does **not** do this. It rescales each
> feature globally and leaves per-channel mean differences fully intact. That was the
> original (wrong) implementation of this control; `test_standardize_features_is_not_the_
> amplitude_control` now documents the distinction.

### Measured result (8 channels, 14 segments = 112 samples, 8 classes, chance 0.125)

| condition | accuracy | chance | ratio | p | |
|---|---|---|---|---|---|
| uncontrolled (raw amplitude) | 0.582 | 0.125 | 4.7× | 0.023 | gain confound present |
| **controlled (unit-sigma)** | **0.394** | 0.125 | **3.1×** | **0.025** | survives the control |

**Interpretation.** Roughly a third of the raw discriminability was per-channel gain.
Accuracy remains ~3.1× chance and significant after gain is removed, so electrodes differ
in signal *structure*, not only in amplitude.

**What this does NOT show.** Not computation. Not learning. Not information processing.
Not that biology beats silicon. It shows electrode-level distinguishability on a live
organoid MEA, measured with a stated control.

### Open confounds

- per-channel electrode impedance (unmeasurable without platform access)
- temporal drift — segments from one electrode are not independent in time
- organoid coverage — an electrode with no tissue is trivially distinguishable
- small n (112 samples, 8 classes)

---

## The initial live-stream characterisation

Preserved as an **initial observation**, not proof of anything larger:

```
channels 10–15 · 8 packets · 3.41 s of signal
noise sigma 5.99–10.66 µV per channel
range −78.4 to +58.5 µV
6σ events: ch12 = 9, ch13 = 1, ch14 = 1
```

**What it establishes.** The pipeline successfully captured and analysed live neural
electrical activity under the tested conditions.

**What it does not establish.** Not biological computation. Not organoid learning. Not
that neurons are computing. Not low-cost AI.

## Provenance

Every run writes a manifest: git commit (and dirty flag), provider config, dataset hash,
seeds, effective processing parameters, model versions, environment, package versions, and
metrics — plus a `fingerprint()` over the reproducibility-relevant fields.

## Adding an experiment

1. Write an `ExperimentSpec` in `experiments/library.py` with `evidence_for` and
   `evidence_against` filled in **before** running anything.
2. Declare the `LabelSource` honestly. If labels are not genuinely known, the experiment
   is descriptive — say so.
3. List `known_confounds` and the control that addresses each.
4. Run through `ExperimentRunner`; never hand-roll evaluation.
