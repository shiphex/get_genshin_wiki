"""Artifacts validation rules."""

from __future__ import annotations

from src.alerts.rules import invalid_artifact_piece_count, missing_required_fields


class ArtifactsValidator:
    """Validate parsed artifacts."""

    namespace = "artifacts"

    def validate(self, record) -> list:
        alerts = []
        missing = [
            field_name
            for field_name in ["title", "url", "fetched_at"]
            if not getattr(record, field_name, "")
        ]
        if missing:
            alerts.append(missing_required_fields(self.namespace, record.title, missing))
        if len(getattr(record.info, "部件列表", [])) < 5:
            alerts.append(invalid_artifact_piece_count(record.title, len(record.info.部件列表)))
        return alerts
