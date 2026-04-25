"""Books validation rules."""

from __future__ import annotations

from src.alerts.rules import empty_book_volumes, missing_required_fields


class BookValidator:
    """Validate parsed books."""

    namespace = "books"

    def validate(self, record) -> list:
        alerts = []
        missing = [
            field_name
            for field_name in ["title", "url", "fetched_at"]
            if not getattr(record, field_name, "")
        ]
        if missing:
            alerts.append(missing_required_fields(self.namespace, record.title, missing))
        if not getattr(record, "volumes", []):
            alerts.append(empty_book_volumes(record.title))
        return alerts
