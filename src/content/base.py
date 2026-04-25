"""Shared content protocols."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CrawlRunResult:
    """Result of a single namespace crawl run."""

    namespace: str
    manifest: dict[str, Any]
    manifest_path: Path
    alerts_path: Path
