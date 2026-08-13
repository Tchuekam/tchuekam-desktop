"""BioCompute -- a provider-independent subsystem for biological neural computing.

    TchueKAM -> BioCompute Core -> Provider Adapter -> Neural Pipeline
             -> Analysis/Decoding -> Benchmarking -> Report

FinalSpark is ONE backend behind this interface, not the architecture. The local
simulator is another. Nothing above the provider layer knows which is in use.

READ-ONLY BY DESIGN. No provider here stimulates biological tissue; the base class
blocks it outright. See docs/biocompute/SAFETY.md.

Top-level imports are kept dependency-light (numpy only). Providers, models and
plots import their heavier dependencies lazily, so `import biocompute` never pulls
scipy/sklearn/matplotlib unless you use those layers.
"""

from biocompute.core.capabilities import (
    Capability,
    CapabilityError,
    ProviderCapabilities,
)
from biocompute.core.provenance import BIOCOMPUTE_VERSION, ExperimentManifest
from biocompute.core.provider import BioComputeProvider, ConnectionInfo
from biocompute.core.registry import available, get_provider, register
from biocompute.core.schema import (
    ChannelLayout,
    DeviceInfo,
    ElectrodePosition,
    Recording,
    RecordRequest,
)

__version__ = BIOCOMPUTE_VERSION

__all__ = [
    "BIOCOMPUTE_VERSION",
    "BioComputeProvider",
    "Capability",
    "CapabilityError",
    "ChannelLayout",
    "ConnectionInfo",
    "DeviceInfo",
    "ElectrodePosition",
    "ExperimentManifest",
    "ProviderCapabilities",
    "Recording",
    "RecordRequest",
    "available",
    "get_provider",
    "register",
    "__version__",
]
