"""Arms validation rules."""

from __future__ import annotations

from src.alerts.rules import missing_required_fields


class ArmsValidator:
    """Validate parsed weapons."""

    namespace = "arms"

    def validate(self, record) -> list:
        missing = [
            field_name
            for field_name in ["title", "url", "fetched_at"]
            if not getattr(record, field_name, "")
        ]
        if missing:
            return [missing_required_fields(self.namespace, record.title, missing)]
        return []
