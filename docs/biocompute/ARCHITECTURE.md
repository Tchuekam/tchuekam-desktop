# BioCompute Platform Architecture

This document specifies the software architecture of the **TchueKAM BioCompute Research Platform**, an enterprise-grade biological and biomorphic neural computing system.

---

## 🏗️ 1. High-Level Architecture Map

```
                                  USER / TCHUEKAM DESKTOP UI
                                                │
                                    [ /biocompute Playground ]
                                                │
                                                ▼
                                TCHUEKAM BACKEND REST/WS API
                                 (tchuekam_backend/api/v1)
                                                │
                                                ▼
                                   BIOCOMPUTE CORE API
                                    (biocompute/core)
                                                │
                                                ▼
                         ┌──────────────────────┴──────────────────────┐
                         │                                             │
                         ▼                                             ▼
                 SIMULATOR PROVIDER                           FINALSPARK PROVIDER
        (biocompute/providers/simulator)             (biocompute/providers/finalspark)
        • Brian2 LIF Spiking Engine                  • Live Socket.IO 3750Hz Feed
        • Ground-Truth Labeled Data                  • 3D Spatial Electrode Map (µm)
        • $0 Offline Execution                       • READ-ONLY Safety Guarantee
                         │                                             │
                         └──────────────────────┬──────────────────────┘
                                                │
                                                ▼
                                  NEURAL SIGNAL PIPELINE
                                   (biocompute/neural)
                        RAW -> Validate -> Filter -> Noise -> Artifact
                            -> Spikes -> Features -> Analysis
                                                │
                                                ▼
                                  RESERVOIR & SNN MODELS
                                   (biocompute/models)
                         • Digital Reservoir (ReservoirPy / ESN)
                         • Spiking Neural Networks (snnTorch / LIF)
                         • Conventional Baselines (Tiny CNN, SVM, RF)
                                                │
                                                ▼
                                  EXPERIMENT & BENCHMARK ENGINE
                                 (biocompute/experiments)
```

---

## 🔒 2. Safety & Read-Only Constraints

1. **Read-Only Guarantee:** The `FinalSparkProvider` enforces read-only access for passive neural recording, microscope image capture, and channel layout discovery.
2. **Blocked Stimulation:** The `stimulate()` primitive raises `PermissionError` at the base class. Any future stimulation capability requires an explicit human-in-the-loop approval gate, validation, and audit log.

---

## 📊 3. Data Schema & Provenance

Every recording is serialized in a provider-neutral `Recording` object containing:
- `experiment_id`, `provider`, `session_id`, `timestamp`
- `sample_rate_hz`, `channels`, `units`, `data` (segmented shape)
- `channel_layout` (3D $\mu\text{m}$ electrode positions)
- `processing_parameters` (every step's effective parameters)
- `data_hash` (SHA-256 for dataset integrity)
- `to_neo()` export capability for standard electrophysiology compatibility.
