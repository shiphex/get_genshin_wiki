"""Cleaned text persistence."""

from __future__ import annotations

from pathlib import Path

from .layout import sanitize_filename


class CleanedStore:
    """Persist cleaned text files."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, title: str, content: str) -> Path:
        output_path = self.output_dir / f"{sanitize_filename(title)}.txt"
        output_path.write_text(content, encoding="utf-8")
        return output_path
