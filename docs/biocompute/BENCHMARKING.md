# BioCompute — Benchmarking

## Purpose

Compare biological and conventional approaches **on an identical task, under identical
conditions**. Not to show biology wins. Most likely it will not, and the benchmark must be
capable of showing that.

## Rules

### 1. Chance is the majority-class rate, not 1/K

With imbalanced labels, `1/n_classes` understates chance and inflates every margin.
`ModelMetrics.chance_accuracy` uses the majority-class rate.

### 2. Beating chance once is not evidence

Small n — and biological datasets are always small n — produces above-chance
cross-validated accuracy by luck routinely. Every claim requires a permutation test:

```
p = (1 + #{null ≥ observed}) / (1 + n_permutations)
```

The `+1` keeps p strictly positive; nothing is ever reported as `p = 0`. The floor is
reported as `min_achievable_p`, so 60 permutations honestly caps you at p ≈ 0.016.

### 3. Selection must be corrected

**This is the subtle one, and we got it wrong first.**

If you evaluate K models and report the best, the best is the maximum of K noisy
estimates and is biased upward. Testing it against a **single-model** null is too lenient.

Measured on genuinely label-free synthetic data (8 seeds, 5 models):

| | mean accuracy on null data |
|---|---|
| logistic_regression | 0.486 |
| svm_rbf | 0.458 |
| random_forest | 0.491 |
| mlp | 0.487 |
| **best-of-5** | **0.537** |

Each model individually is unbiased. The *selection* adds ~+0.04. With the single-model
null, our E1 null control returned **p = 0.030 — a false positive on data with no signal
at all**. With `permutation_test_best_of()`, which applies the same selection inside every
permutation, the same data returned **p = 0.111**, correctly non-significant.

Use `permutation_test_best_of()` whenever you report a winner.

### 4. Unmeasured is `None`

`energy_joules` and `cost_usd` default to `None` and are never estimated, extrapolated, or
taken from a vendor claim. The table renders them as `n/m`.

A benchmark that compares accuracy and speed but not economics is a valid benchmark. One
that invents an energy number is not.

### 5. No silent caps

If a runtime budget reduces the permutation count, `budget_note` says so and the reduction
appears in the result. Truncation that is not reported reads as full coverage.

## Running

```bash
python -m biocompute.cli benchmark --classes 2 --trials 40 --permutations 60 --report
```

Measured output (simulator, ground-truth labels, 80 samples, 56 features):

```
model                        acc    +/-  chance  margin        p  train_s  infer_s  energy   cost
majority_class             0.500  0.000   0.500  +0.000   1.0000    0.000   0.0001     n/m    n/m
logistic_regression        0.975  0.050   0.500  +0.475   0.0164    0.068   0.0047     n/m    n/m
svm_rbf                    0.963  0.031   0.500  +0.463   0.0164    0.017   0.0045     n/m    n/m
random_forest              1.000  0.000   0.500  +0.500   0.0164    1.081   0.0676     n/m    n/m
mlp                        0.988  0.025   0.500  +0.487   0.0164    0.520   0.0050     n/m    n/m
reservoir_digital_esn      0.925  0.061   0.500  +0.425   0.0164    0.091   0.0173     n/m    n/m
```

`p = 0.0164 = 1/61` is the floor at 60 permutations, not a coincidence.

## Digital vs biological reservoir

`ReservoirModel` takes a swappable `ReservoirBackend`:

```
input encoder → reservoir → ridge readout → prediction
```

Only the readout is trained. That is what makes reservoir computing the one architecture
where biological substrate is plausible at all: it sidesteps credit assignment, which is
otherwise fatal because individual synapses cannot be addressed.

`DigitalReservoir` (echo-state network, pure numpy) is the baseline.
`BiologicalReservoirStub` documents the contract and **raises on use** — it needs
stimulation, which BioCompute does not implement. Its docstring records the constraint that
should shape any future encoder design: uploading stimulation parameters costs ~10 s plus a
recording blackout, so a real biological reservoir must hold its mapping fixed across a run
and vary only which trigger fires.

## What this benchmark cannot tell you

- **Nothing about energy or cost**, until those are measured on real hardware.
- **Nothing about biological superiority.** No biological reservoir exists here.
- **Nothing that generalises from the simulator to tissue.** The simulator is a test
  instrument, not a biophysical model.

Any claim beyond "these decoders achieved these accuracies on this task" is unsupported by
this engine.
