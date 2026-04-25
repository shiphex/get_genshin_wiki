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
        piece_count = len(getattr(record.info, "部件列表", []))
        if piece_count == 0:
            alerts.append(invalid_artifact_piece_count(record.title, piece_count))
        elif piece_count > 0 and piece_count < 5:
            # Single-piece artifacts (like 祭火之人) are valid, but flag as warning
            alerts.append(missing_required_fields(self.namespace, record.title, [f"部件数不足5，仅有{piece_count}个部件"]))
        return alerts
