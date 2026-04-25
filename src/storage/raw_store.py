"""Raw content persistence."""

from __future__ import annotations

from pathlib import Path

from .layout import sanitize_filename


class RawStore:
    """Persist raw HTML or source payloads."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, title: str, content: str, suffix: str = ".html") -> Path:
        output_path = self.output_dir / f"{sanitize_filename(title)}{suffix}"
        output_path.write_text(content, encoding="utf-8")
        return output_path
