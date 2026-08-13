# BioCompute Safety & Ethical Framework

This document outlines the safety constraints, ethical guidelines, and access controls enforced across the TchueKAM BioCompute Research Platform.

---

## 🛑 1. The Read-Only Safety Constraint

1. **No Autonomous Stimulation:** The platform operates in **read-only mode** by default when connecting to live biological hardware (FinalSpark NeuroPlatform).
2. **Blocked Method:** Calling `stimulate()` on `BioComputeProvider` raises an unbypassable `PermissionError`.
3. **Hardware Preservation:** Biological organoids are shared living assets with finite lifetimes (2–12 weeks). Uncontrolled high-amplitude or high-frequency electrical pulses mutate cellular structures and degrade tissue health.

---

## 🔐 2. Future Stimulation Approval Architecture

If electrical stimulation capabilities are added in future releases, they MUST adhere to the 5-stage human-approval architecture:

```
TchueKAM Agent Proposal
          │
          ▼
Input Parameter Validation (Safe Range Checks: Amplitude ≤ 1.0 µA, Duration ≤ 500 µs, Charge Balance)
          │
          ▼
Explicit Human Operator Approval (Interactive UI Gate)
          │
          ▼
Authorized Execution (Token-authenticated & Time-bounded)
          │
          ▼
Immutable Audit Log (Timestamp, Parameters, User ID)
```

---

## 🚫 3. Non-Clinical Use Disclaimer

1. **Research & Benchmarking Only:** The BioCompute platform is designed exclusively for artificial intelligence research, biological reservoir computing, and neuromorphic benchmarking.
2. **No Medical Claims:** The platform must **NEVER** be used to make clinical diagnoses, detect medical diseases in human patients, or prescribe medical treatments.
