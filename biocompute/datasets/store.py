"""Dataset storage: recordings + their manifests, kept together.

A recording without its manifest is not a dataset -- it is an array of numbers with
no provenance. This module always writes both.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from biocompute.core.provenance import ExperimentManifest
from biocompute.core.schema import Recording

DEFAULT_ROOT = Path("biocompute_data")


class DatasetStore:
    """Flat, inspectable, git-friendly dataset directory."""

    def __init__(self, root: str | Path = DEFAULT_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _paths(self, dataset_id: str) -> tuple[Path, Path]:
        return (self.root / f"{dataset_id}.h5", self.root / f"{dataset_id}.manifest.json")

    def save(self, recording: Recording, dataset_id: str | None = None,
             notes: list[str] | None = None) -> dict[str, str]:
        dataset_id = dataset_id or (
            f"{recording.provider}-{recording.experiment_id}-{recording.data_hash()}"
        )
        h5_path, man_path = self._paths(dataset_id)
        recording.to_hdf5(str(h5_path))

        manifest = ExperimentManifest.create(
            name=f"dataset-{dataset_id}",
            provider=recording.provider,
            provider_config=recording.provider_metadata,
            dataset_hash=recording.data_hash(),
            dataset_reference=str(h5_path),
            processing_parameters=[
                {"name": s.name, "params": s.params} for s in recording.processing_parameters
            ],
            data_source_is_biological=bool(
                (recording.provider_metadata or {}).get("biological", False)
            ),
            notes=notes or [],
        )
        manifest.save(man_path)
        return {"dataset_id": dataset_id, "data": str(h5_path), "manifest": str(man_path)}

    def load(self, dataset_id: str) -> tuple[Recording, ExperimentManifest | None]:
        h5_path, man_path = self._paths(dataset_id)
        if not h5_path.exists():
            raise FileNotFoundError(f"no dataset '{dataset_id}' in {self.root}")
        rec = Recording.from_hdf5(str(h5_path))
        man = ExperimentManifest.load(man_path) if man_path.exists() else None
        return rec, man

    def list(self) -> list[dict]:
        out = []
        for h5 in sorted(self.root.glob("*.h5")):
            dataset_id = h5.stem
            entry = {"dataset_id": dataset_id, "data": str(h5),
                     "size_bytes": h5.stat().st_size, "manifest": None}
            man_path = self.root / f"{dataset_id}.manifest.json"
            if man_path.exists():
                m = json.loads(man_path.read_text(encoding="utf-8"))
                entry["manifest"] = {
                    "provider": m.get("provider"),
                    "created_at": m.get("created_at"),
                    "dataset_hash": m.get("dataset_hash"),
                    "biological": m.get("data_source_is_biological"),
                    "git_commit": (m.get("git_commit") or "")[:8] or None,
                }
            out.append(entry)
        return out

    def write_index(self) -> str:
        path = self.root / "index.json"
        path.write_text(
            json.dumps(
                {"generated_at": datetime.now(timezone.utc).isoformat(),
                 "root": str(self.root), "datasets": self.list()},
                indent=2, default=str,
            ),
            encoding="utf-8",
        )
        return str(path)
