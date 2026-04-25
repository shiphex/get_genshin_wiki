"""Cleaned content persistence."""

from __future__ import annotations

import json
from pathlib import Path


class CleanedStore:
    """Persist cleaned content into one JSON file."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, title: str, content: str, metadata: dict | None = None) -> Path:
        payload = {
            "title": title,
            "content_clean": content,
        }
        if metadata:
            for key in ("url", "fetched_at"):
                value = metadata.get(key)
                if value:
                    payload[key] = value

        records = self._load_records()
        index_by_title = {record.get("title"): idx for idx, record in enumerate(records) if record.get("title")}
        existing_index = index_by_title.get(title)
        if existing_index is None:
            records.append(payload)
        else:
            records[existing_index] = payload

        self.file_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.file_path

    def _load_records(self) -> list[dict]:
        if not self.file_path.exists():
            return []

        try:
            raw_data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        if isinstance(raw_data, list):
            return [record for record in raw_data if isinstance(record, dict)]
        return []
