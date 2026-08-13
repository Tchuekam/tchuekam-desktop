# BioCompute — Providers

A provider is a source of neural data. Nothing above the provider layer knows which one is
in use.

## Registered providers

| | `simulator` | `finalspark` |
|---|---|---|
| Biological | no | **yes** (human iPSC-derived organoids) |
| Read-only | yes | yes |
| Shared resource | no | **yes** |
| Network | none | public HTTPS + Socket.IO |
| Auth | none | **none — public scope only** |
| RECORDING | ✅ | ✅ |
| STREAMING | ✅ | ❌ *(see below)* |
| LAYOUT | ✅ | ✅ |
| METADATA | ✅ | ❌ (needs a platform token) |
| MICROSCOPY | ❌ | ✅ |
| ENVIRONMENT | ❌ | ❌ (needs a platform token) |
| STIMULATION | ❌ | ❌ **blocked by design** |

### Why FinalSpark does not declare STREAMING

It pushes data over a socket, but delivery is throttled and gappy — measured at 0.6–20 s
between 0.427 s packets, scaling with channel count because payloads are JSON text against
a 1 MB server ceiling. Declaring STREAMING would tell callers they can assume gapless
coverage. They cannot.

Recordings from this provider are marked `contiguous=False`, and `assert_contiguous()`
rejects any analysis that assumes otherwise.

## `simulator`

Deterministic, seeded, offline. **A test instrument, not a biophysical model** — no
membrane equations, no synapses, no plasticity.

It models what the pipeline must handle: per-channel firing rates and noise sigma, biphasic
spike waveforms with jitter, burst episodes, a shared latent drive producing cross-channel
correlation, and stimulus-conditioned responses that provide ground-truth labels.

```python
from biocompute.providers.simulator.adapter import SimulatorProvider

sim = SimulatorProvider(n_channels=8, seed=0)
rec = sim.record_labeled(n_classes=2, trials_per_class=40)          # real signal
null = sim.record_labeled(n_classes=2, trials_per_class=40, response_gain=0.0)  # null control
```

`response_gain=0.0` produces a **null dataset** where classes are statistically identical.
Use it as the negative control for any decoding claim.

If biophysical realism is needed later, Brian2 / NEST / Norse would go behind this same
interface as a separate provider. None is installed, because nothing needs one yet.

## `finalspark`

Live human brain-organoid activity from FinalSpark's public service. No account required.

```python
from biocompute.core.registry import get_provider
from biocompute.core.schema import RecordRequest

p = get_provider("finalspark")
print(p.connect().detail)                 # "5/6 controllers usable"
devices = [d for d in p.discover() if d.usable]
rec = p.record(RecordRequest(channels=[0,1,2,3], n_segments=4, timeout_s=180))
```

Signal: 3750 Hz, microvolts, 1600 samples (0.4267 s) per segment.
See [NEURAL_DATA.md](NEURAL_DATA.md) for the aliasing caveat.

**Operational courtesy** — this is shared infrastructure serving a public page:

- request the fewest channels you need; throughput degrades sharply with channel count
- keep recordings small; retries are capped at 2 with backoff
- live tests are marked `integration` and excluded from default runs
- never authenticate, never bypass booking or rate limits

`livenp.finalspark.com` is undocumented and may change without notice — FinalSpark's own
client libraries already broke this way.

## Writing a new provider

```python
from biocompute.core.capabilities import Capability, ProviderCapabilities
from biocompute.core.provider import BioComputeProvider, ConnectionInfo

class MyProvider(BioComputeProvider):
    name = "my_rig"
    capabilities = ProviderCapabilities.of(Capability.RECORDING, Capability.LAYOUT)
    read_only = True

    def connect(self) -> ConnectionInfo: ...
    def discover(self) -> list[DeviceInfo]: ...
    def record(self, request: RecordRequest) -> Recording: ...
```

Register it:

```python
from biocompute.core.registry import register
register("my_rig", MyProvider)
```

Rules:

1. **Declare only what you actually support.** Unsupported calls must raise
   `CapabilityError`, never return fabricated data.
2. **Set `contiguous` honestly.** False if there is any gap between segments.
3. **Preserve provider-specific fields** in `provider_metadata` — do not discard them.
4. **Record acquisition parameters** via `add_processing_step()`.
5. **Never implement `stimulate()`.** It is blocked at the base class; see
   [SAFETY.md](SAFETY.md).
