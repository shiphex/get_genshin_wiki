"""Alert collection and persistence."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Alert:
    """Structured runtime alert."""

    level: str
    code: str
    message: str
    namespace: str
    title: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "namespace": self.namespace,
            "title": self.title,
            "extra": self.extra,
            "created_at": self.created_at,
        }


class AlertReporter:
    """Collect alerts and persist them per run."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.alerts: list[Alert] = []

    def add(self, alert: Alert) -> None:
        self.alerts.append(alert)
        log_message = f"[{alert.namespace}] {alert.code}: {alert.message}"
        if alert.level == "error":
            logger.error(log_message)
        elif alert.level == "warning":
            logger.warning(log_message)
        else:
            logger.info(log_message)

    def extend(self, alerts: list[Alert]) -> None:
        for alert in alerts:
            self.add(alert)

    def count(self, level: str) -> int:
        return sum(1 for alert in self.alerts if alert.level == level)

    def save(self, run_id: str) -> Path:
        output_path = self.output_dir / f"alerts_{run_id}.json"
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(
                [alert.to_dict() for alert in self.alerts],
                file,
                ensure_ascii=False,
                indent=2,
            )
        return output_path
