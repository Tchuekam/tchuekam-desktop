"""Experiment provenance: everything needed to reproduce a run.

If a number cannot be traced back to a commit, a seed, a dataset hash and a
parameter set, it is not a result. This module makes that traceability automatic
rather than a discipline someone has to remember.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BIOCOMPUTE_VERSION = "0.1.0"

TRACKED_PACKAGES = ("numpy", "scipy", "scikit-learn", "h5py", "matplotlib", "python-socketio")


def git_commit(repo_root: str | None = None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root or str(Path(__file__).resolve().parents[2]),
            capture_output=True, text=True, timeout=10, check=False,
        )
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def git_dirty(repo_root: str | None = None) -> bool | None:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root or str(Path(__file__).resolve().parents[2]),
            capture_output=True, text=True, timeout=10, check=False,
        )
        return bool(out.stdout.strip())
    except Exception:  # noqa: BLE001
        return None


def package_versions() -> dict[str, str | None]:
    from importlib.metadata import PackageNotFoundError, version

    out: dict[str, str | None] = {}
    for pkg in TRACKED_PACKAGES:
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = None
    return out


def environment() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "packages": package_versions(),
    }


@dataclass
class ExperimentManifest:
    """The reproducibility record for one experiment run."""

    experiment_id: str
    name: str
    created_at: str
    biocompute_version: str = BIOCOMPUTE_VERSION
    git_commit: str | None = None
    git_dirty: bool | None = None
    provider: str | None = None
    provider_config: dict[str, Any] = field(default_factory=dict)
    dataset_hash: str | None = None
    dataset_reference: str | None = None
    random_seeds: dict[str, int] = field(default_factory=dict)
    processing_parameters: list[dict[str, Any]] = field(default_factory=list)
    model_versions: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=environment)
    metrics: dict[str, Any] = field(default_factory=dict)
    data_source_is_biological: bool | None = None
    notes: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, name: str, **kwargs) -> ExperimentManifest:
        return cls(
            experiment_id=f"{name}-{uuid.uuid4().hex[:8]}",
            name=name,
            created_at=datetime.now(timezone.utc).isoformat(),
            git_commit=git_commit(),
            git_dirty=git_dirty(),
            **kwargs,
        )

    def fingerprint(self) -> str:
        """Stable hash of the reproducibility-relevant fields (not the metrics)."""
        payload = {
            "git_commit": self.git_commit,
            "provider": self.provider,
            "provider_config": self.provider_config,
            "dataset_hash": self.dataset_hash,
            "random_seeds": self.random_seeds,
            "processing_parameters": self.processing_parameters,
            "model_versions": self.model_versions,
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fingerprint"] = self.fingerprint()
        return d

    def save(self, path: str | Path) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8")
        return str(path)

    @classmethod
    def load(cls, path: str | Path) -> ExperimentManifest:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        d.pop("fingerprint", None)
        return cls(**d)
