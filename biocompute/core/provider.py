"""The provider interface every biological-compute backend implements.

A provider is a source of neural data. FinalSpark is one. The local simulator is
another. Future MEA rigs would be more. Nothing above this layer should know which.

Only `discover()` and `record()` are abstract. Everything else is capability-gated:
the default implementation raises CapabilityError, so a provider implements exactly
what it supports and no more.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from biocompute.core.capabilities import Capability, ProviderCapabilities
from biocompute.core.schema import ChannelLayout, DeviceInfo, Recording, RecordRequest


@dataclass
class ConnectionInfo:
    """Result of connect(): whether the backend is reachable and what it reports."""

    provider: str
    reachable: bool
    detail: str = ""
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BioComputeProvider(ABC):
    """Base class for every neural-data provider."""

    name: str = "unnamed"
    capabilities: ProviderCapabilities = ProviderCapabilities.of()

    #: Providers that touch shared or living hardware set this True so callers
    #: can apply extra care (rate limits, booking checks, no hammering).
    shared_resource: bool = False

    #: Read-only providers cannot mutate the biological system in any way.
    read_only: bool = True

    # ------------------------------------------------------------- required

    @abstractmethod
    def connect(self) -> ConnectionInfo:
        """Check reachability. Must not mutate anything."""

    @abstractmethod
    def discover(self) -> list[DeviceInfo]:
        """List addressable devices."""

    @abstractmethod
    def record(self, request: RecordRequest) -> Recording:
        """Acquire a bounded Recording. Must respect request limits."""

    # --------------------------------------------------- capability-gated

    def get_layout(self, device_id: str | None = None, mea_index: int | None = None) -> ChannelLayout:
        self.capabilities.require(self.name, Capability.LAYOUT)
        raise NotImplementedError  # pragma: no cover - provider must override

    def capture_image(self, device_id: str | None = None, mea_index: int | None = None) -> bytes:
        self.capabilities.require(self.name, Capability.MICROSCOPY)
        raise NotImplementedError  # pragma: no cover

    def get_sample_metadata(self, device_id: str | None = None) -> dict[str, Any]:
        self.capabilities.require(self.name, Capability.METADATA)
        raise NotImplementedError  # pragma: no cover

    def get_environment(self, device_id: str | None = None) -> dict[str, Any]:
        self.capabilities.require(self.name, Capability.ENVIRONMENT)
        raise NotImplementedError  # pragma: no cover

    # ------------------------------------------------------------- guard

    def stimulate(self, *args, **kwargs):
        """Permanently blocked at the base class.

        Stimulation mutates living tissue on shared, booked hardware. It is out of
        scope for this subsystem by design. A future implementation must live in a
        separate module behind an explicit human-approval gate and audit log --
        never as a silent override of this method.
        """
        raise PermissionError(
            "Stimulation is not implemented in BioCompute and must not be added here. "
            "See docs/biocompute/SAFETY.md for the required approval architecture."
        )

    # ------------------------------------------------------------- helpers

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capabilities": self.capabilities.as_list(),
            "read_only": self.read_only,
            "shared_resource": self.shared_resource,
        }
