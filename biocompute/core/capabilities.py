"""Provider capability declaration.

A provider advertises only what it can actually do. Callers ask before they act.
Nothing is forced to implement functionality it does not support -- an unsupported
call raises CapabilityError rather than returning fabricated data.

STIMULATION is defined here so the vocabulary is complete and so guards can name
it, but **no provider in this codebase implements it**. See docs/biocompute/SAFETY.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Capability(str, Enum):
    """Things a biological-compute provider might support."""

    RECORDING = "recording"
    """Return a finite Recording of neural signal."""

    STREAMING = "streaming"
    """Deliver signal continuously as it is produced."""

    LAYOUT = "layout"
    """Report physical electrode positions."""

    MICROSCOPY = "microscopy"
    """Return images of the biological sample."""

    METADATA = "metadata"
    """Report culture/sample metadata (age, batch, medium...)."""

    ENVIRONMENT = "environment"
    """Report incubator conditions (temperature, CO2, flow rate...)."""

    STIMULATION = "stimulation"
    """Deliver electrical stimulation to living tissue.

    NOT IMPLEMENTED BY ANY PROVIDER HERE, BY DESIGN. Any future implementation
    must sit behind an explicit human-approval gate and a separate safety layer.
    """


class CapabilityError(NotImplementedError):
    """Raised when a caller requests something the provider does not support."""

    def __init__(self, provider: str, capability: Capability, detail: str = ""):
        self.provider = provider
        self.capability = capability
        msg = f"provider '{provider}' does not support capability '{capability.value}'"
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)


@dataclass(frozen=True)
class ProviderCapabilities:
    """Immutable set of capabilities a provider advertises."""

    supported: frozenset[Capability]

    @classmethod
    def of(cls, *caps: Capability) -> ProviderCapabilities:
        return cls(frozenset(caps))

    def supports(self, capability: Capability) -> bool:
        return capability in self.supported

    def require(self, provider_name: str, capability: Capability, detail: str = "") -> None:
        """Raise CapabilityError unless `capability` is supported."""
        if not self.supports(capability):
            raise CapabilityError(provider_name, capability, detail)

    def as_list(self) -> list[str]:
        return sorted(c.value for c in self.supported)

    def __contains__(self, capability: object) -> bool:
        return capability in self.supported
