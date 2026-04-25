"""Manifest persistence."""

from __future__ import annotations

import json
from pathlib import Path


class ManifestStore:
    """Persist per-run manifests."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, manifest: dict, run_id: str) -> Path:
        output_path = self.output_dir / f"manifest_{run_id}.json"
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(manifest, file, ensure_ascii=False, indent=2)
        return output_path
