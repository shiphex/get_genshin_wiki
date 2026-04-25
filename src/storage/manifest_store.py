"""Manifest persistence."""

from __future__ import annotations

import json
from pathlib import Path

from .atomic_write import atomic_write_text


class ManifestStore:
    """Persist per-run manifests."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, manifest: dict, run_id: str) -> Path:
        output_path = self.output_dir / f"manifest_{run_id}.json"
        atomic_write_text(
            output_path,
            json.dumps(manifest, ensure_ascii=False, indent=2),
            temp_file_path=output_path.with_suffix(f"{output_path.suffix}.tmp"),
            backup_file_path=output_path.with_suffix(f"{output_path.suffix}.bak"),
        )
        return output_path
