"""Failure persistence."""

from __future__ import annotations

from pathlib import Path


class FailureStore:
    """Persist failed titles."""

    def __init__(self, file_path: str | Path, legacy_paths: list[str | Path] | None = None):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.legacy_paths = [Path(path) for path in legacy_paths or []]

    def append(self, title: str, reason: str) -> Path:
        with self.file_path.open("a", encoding="utf-8") as file:
            file.write(f"{title}\t{reason}\n")
        return self.file_path

    def load_titles(self) -> set[str]:
        titles = set()
        paths = list(dict.fromkeys([self.file_path, *self.legacy_paths]))
        for path in paths:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as file:
                for line in file:
                    parts = line.strip().split("\t")
                    if parts and parts[0]:
                        titles.add(parts[0])
        return titles
