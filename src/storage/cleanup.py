"""Cleanup helpers for generated crawl artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .layout import build_storage_layout, resolve_legacy_namespace_dirs

FILE_TYPE_EXTENSIONS = {
    "html": ".html",
    "json": ".json",
    "jsonl": ".jsonl",
    "txt": ".txt",
}

NAMESPACE_PROJECTS = {"books", "arms", "artifacts"}
PROJECT_CHOICES = ("tests", "books", "arms", "artifacts", "final-json", "final-jsonl")
FILE_TYPE_CHOICES = tuple(FILE_TYPE_EXTENSIONS.keys())
TEMP_SUBDIRS = ("raw", "failed", "alerts", "manifests")


@dataclass(frozen=True, slots=True)
class CleanupResult:
    removed_files: list[Path]
    removed_dirs: list[Path]

    @property
    def removed_count(self) -> int:
        return len(self.removed_files) + len(self.removed_dirs)


def normalize_choices(values: Iterable[str] | None, allowed: tuple[str, ...]) -> list[str]:
    if not values:
        return list(allowed)

    normalized = []
    seen = set()
    for value in values:
        if value not in allowed:
            raise ValueError(f"Unsupported choice: {value}")
        if value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def collect_cleanup_targets(
    storage_config: dict[str, str] | None = None,
    projects: Iterable[str] | None = None,
    file_types: Iterable[str] | None = None,
    include_cache: bool = False,
    include_logs: bool = False,
    root_dir: str | Path = ".",
) -> list[Path]:
    root_path = Path(root_dir)
    storage_config = storage_config or {}
    selected_projects = normalize_choices(projects, PROJECT_CHOICES)
    selected_types = normalize_choices(file_types, FILE_TYPE_CHOICES)
    selected_suffixes = {FILE_TYPE_EXTENSIONS[file_type] for file_type in selected_types}

    targets: list[Path] = []

    if "tests" in selected_projects:
        targets.extend(_collect_matching_files(root_path / "tests" / "output", selected_suffixes))

    for namespace in [project for project in selected_projects if project in NAMESPACE_PROJECTS]:
        layout = build_storage_layout(storage_config, namespace, create_dirs=False)
        legacy_roots = resolve_legacy_namespace_dirs(storage_config, namespace)
        targets.extend(_collect_namespace_temp_files(namespace, [layout.base_dir, *legacy_roots], selected_suffixes))

    if "final-json" in selected_projects and ".json" in selected_suffixes:
        for namespace in NAMESPACE_PROJECTS:
            layout = build_storage_layout(storage_config, namespace, create_dirs=False)
            targets.append(layout.cleaned_file)
            targets.append(layout.cleaned_backup_file)

    if "final-jsonl" in selected_projects and ".jsonl" in selected_suffixes:
        for namespace in NAMESPACE_PROJECTS:
            layout = build_storage_layout(storage_config, namespace, create_dirs=False)
            targets.append(layout.structured_file)
            for legacy_root in resolve_legacy_namespace_dirs(storage_config, namespace):
                targets.append(legacy_root / f"{namespace}.jsonl")
                targets.append(legacy_root / "structured" / f"{namespace}.jsonl")

    if include_cache:
        targets.extend(_collect_cache_entries(root_path))

    if include_logs:
        targets.extend(_collect_log_files(root_path))

    unique_targets: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        if not target.exists():
            continue
        resolved = target.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_targets.append(target)
    return unique_targets


def cleanup_paths(paths: Iterable[Path], dry_run: bool = False) -> CleanupResult:
    removed_files: list[Path] = []
    removed_dirs: list[Path] = []

    for path in sorted(paths, key=lambda item: (item.is_dir(), len(item.parts)), reverse=True):
        if not path.exists():
            continue
        if dry_run:
            if path.is_dir():
                removed_dirs.append(path)
            else:
                removed_files.append(path)
            continue

        if path.is_dir():
            for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()
            removed_dirs.append(path)
        else:
            path.unlink()
            removed_files.append(path)

    return CleanupResult(removed_files=removed_files, removed_dirs=removed_dirs)


def _collect_matching_files(root: Path, suffixes: set[str]) -> list[Path]:
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes]


def _collect_namespace_temp_files(namespace: str, roots: list[Path], suffixes: set[str]) -> list[Path]:
    targets: list[Path] = []
    cleaned_suffixes = suffixes - {".json"}
    structured_suffixes = suffixes - {".jsonl"}

    for root in roots:
        for subdir in TEMP_SUBDIRS:
            targets.extend(_collect_matching_files(root / subdir, suffixes))

        if cleaned_suffixes:
            targets.extend(_collect_matching_files(root / "cleaned", cleaned_suffixes))
        if structured_suffixes:
            targets.extend(_collect_matching_files(root / "structured", structured_suffixes))

        legacy_failed = root / f"failed_{namespace}.txt"
        if legacy_failed.suffix.lower() in suffixes and legacy_failed.exists():
            targets.append(legacy_failed)

    return targets


def _collect_cache_entries(root: Path) -> list[Path]:
    cache_entries: list[Path] = []
    for directory in root.rglob("__pycache__"):
        if directory.is_dir():
            cache_entries.append(directory)

    pytest_cache = root / ".pytest_cache"
    if pytest_cache.exists():
        cache_entries.append(pytest_cache)

    for file_path in root.rglob("*.pyc"):
        if file_path.is_file():
            cache_entries.append(file_path)

    return cache_entries


def _collect_log_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.log") if path.is_file()]
