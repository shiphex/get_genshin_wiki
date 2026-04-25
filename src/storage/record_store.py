"""Structured record persistence."""

from __future__ import annotations

import json
from pathlib import Path


class RecordStore:
    """Append JSONL records and load saved titles."""

    def __init__(self, file_path: str | Path, legacy_paths: list[str | Path] | None = None):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.legacy_paths = [Path(path) for path in legacy_paths or []]

    def append(self, record: dict) -> Path:
        with self.file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self.file_path

    def load_titles(self) -> set[str]:
        titles = set()
        paths = list(dict.fromkeys([self.file_path, *self.legacy_paths]))
        for path in paths:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as file:
                for line in file:
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    title = data.get("title")
                    if title:
                        titles.add(title)
        return titles
