"""Provider registry -- resolve a provider by name without importing it eagerly.

Providers are imported lazily so that `biocompute` stays importable with only
numpy present. The FinalSpark adapter needs `python-socketio`; the simulator needs
nothing extra. Neither should be a hard import cost for a caller that wants the
other.
"""

from __future__ import annotations

from typing import Callable

from biocompute.core.provider import BioComputeProvider

_BUILTIN: dict[str, str] = {
    "simulator": "biocompute.providers.simulator.adapter:SimulatorProvider",
    "finalspark": "biocompute.providers.finalspark.adapter:FinalSparkProvider",
}

_EXTRA: dict[str, Callable[..., BioComputeProvider]] = {}


def register(name: str, factory: Callable[..., BioComputeProvider]) -> None:
    """Register a provider factory at runtime (for third-party backends)."""
    _EXTRA[name] = factory


def available() -> list[str]:
    return sorted(set(_BUILTIN) | set(_EXTRA))


def get_provider(name: str, **kwargs) -> BioComputeProvider:
    """Instantiate a provider by name."""
    if name in _EXTRA:
        return _EXTRA[name](**kwargs)
    if name not in _BUILTIN:
        raise KeyError(f"unknown provider '{name}'; available: {available()}")
    module_path, _, cls_name = _BUILTIN[name].partition(":")
    import importlib

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:  # pragma: no cover - depends on optional extras
        raise ImportError(
            f"provider '{name}' requires extra dependencies: {e}. "
            f"Install with: pip install -e '.[biocompute]'"
        ) from e
    return getattr(module, cls_name)(**kwargs)
