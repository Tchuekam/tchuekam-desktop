---
name: biocompute-researcher
description: >
  Formulate hypotheses, design experiments, run biological/spiking neural simulations,
  query live FinalSpark MEA organoid feeds, process electrophysiological signals,
  benchmark reservoir and SNN models against conventional baselines, and generate
  reproducible scientific reports.
version: 1.0.0
author: Tchuekam Agent
license: MIT
metadata:
  tchuekam:
    tags: [biocompute, neuroscience, organoid, spiking-neural-networks, reservoir-computing, benchmarking]
    related_skills: [finalspark-livemea, uv, python-data-science]
prerequisites:
  commands: [uv, python]
---

# BioCompute Researcher Skill

Formulate, execute, and analyze biological and biomorphic neural computing experiments.

## Core Rules

- **Epistemological Integrity:** Distinguish `FACT`, `MEASUREMENT`, `INFERENCE`, `HYPOTHESIS`, and `SPECULATION`. Never turn an inference into an unsupported scientific claim.
- **Read-Only Safety:** Operating against biological MEA systems (FinalSpark) is strictly read-only for passive recording and stream monitoring. Autonomous tissue stimulation is blocked.
- **Reproducibility:** Every experiment manifest must record random seeds, software/library versions, git commit hash, and raw dataset references.

## Usage

### 1. Run Benchmark Experiment #1 (Visual Classification)

```bash
uv run -m biocompute.cli run-exp001 --samples 200 --classes 5
```

### 2. Inspect Available BioCompute Providers

```bash
uv run -m biocompute.cli providers
```

### 3. Record & Analyze Simulated Spiking Neural Signals

```bash
uv run -m biocompute.cli simulate --channels 16 --duration 0.427 --out sim_recording.h5
```

### 4. Query Live Biological MEA Organoid Signals

```bash
uv run -m biocompute.cli live-record --channels 0-7 --packets 3 --out live_recording.h5
```

### 5. Generate Experiment Summary Report

```bash
uv run -m biocompute.cli report --manifest biocompute_runs/EXP-001.manifest.json
```
