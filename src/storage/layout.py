"""Storage path resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LEGACY_STORAGE_KEYS = {
    "books": ("books_dir", "book_dir"),
    "arms": ("arms_dir", "arm_dir"),
    "artifacts": ("artifacts_dir", "artifact_dir"),
}

NAMESPACE_DIR_ALIASES = {
    "books": ("books", "book"),
    "arms": ("arms", "arm"),
    "artifacts": ("artifacts",),
}


@dataclass(frozen=True, slots=True)
class StorageLayout:
    namespace: str
    base_dir: Path
    raw_dir: Path
    cleaned_dir: Path
    cleaned_file: Path
    cleaned_temp_file: Path
    cleaned_backup_file: Path
    structured_dir: Path
    alerts_dir: Path
    manifests_dir: Path
    structured_file: Path
    failed_dir: Path
    failed_file: Path


def sanitize_filename(name: str) -> str:
    """Make titles safe for Windows paths."""
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return safe or "untitled"


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    unique_paths: list[Path] = []
    seen_paths: set[Path] = set()
    for path in paths:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        unique_paths.append(path)
    return unique_paths


def _candidate_namespace_dirs(
    storage_config: dict[str, Any], namespace: str, base_dir: str | None = None
) -> list[Path]:
    if base_dir:
        return [Path(base_dir)]

    configured_dirs = [
        Path(storage_config[key])
        for key in LEGACY_STORAGE_KEYS.get(namespace, ())
        if storage_config.get(key)
    ]
    output_dir = Path(storage_config.get("output_dir", "storage"))
    alias_dirs = [output_dir / alias for alias in NAMESPACE_DIR_ALIASES.get(namespace, (namespace,))]
    return _dedupe_paths([*configured_dirs, *alias_dirs])


def resolve_namespace_dir(storage_config: dict[str, Any], namespace: str, base_dir: str | None = None) -> Path:
    return _candidate_namespace_dirs(storage_config, namespace, base_dir=base_dir)[0]


def resolve_legacy_namespace_dirs(
    storage_config: dict[str, Any], namespace: str, base_dir: str | None = None
) -> list[Path]:
    primary_dir = resolve_namespace_dir(storage_config, namespace, base_dir=base_dir)
    return [path for path in _candidate_namespace_dirs(storage_config, namespace, base_dir=base_dir) if path != primary_dir]


def build_storage_layout(
    storage_config: dict[str, Any],
    namespace: str,
    base_dir: str | None = None,
    create_dirs: bool = True,
) -> StorageLayout:
    root = resolve_namespace_dir(storage_config, namespace, base_dir=base_dir)
    raw_dir = root / "raw"
    cleaned_dir = root / "cleaned"
    structured_dir = root / "structured"
    alerts_dir = root / "alerts"
    manifests_dir = root / "manifests"
    failed_dir = root / "failed"

    if create_dirs:
        for directory in [root, raw_dir, cleaned_dir, structured_dir, alerts_dir, manifests_dir, failed_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    return StorageLayout(
        namespace=namespace,
        base_dir=root,
        raw_dir=raw_dir,
        cleaned_dir=cleaned_dir,
        cleaned_file=cleaned_dir / f"{namespace}.json",
        cleaned_temp_file=cleaned_dir / f".{namespace}.json.tmp",
        cleaned_backup_file=cleaned_dir / f"{namespace}.json.bak",
        structured_dir=structured_dir,
        alerts_dir=alerts_dir,
        manifests_dir=manifests_dir,
        structured_file=structured_dir / f"{namespace}.jsonl",
        failed_dir=failed_dir,
        failed_file=failed_dir / f"failed_{namespace}.txt",
    )
