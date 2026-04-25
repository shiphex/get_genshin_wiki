"""Cleaned content persistence."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .atomic_write import (
    AtomicWriteRollbackToken,
    destination_temp_path,
    rollback_atomic_write,
)


class CleanedStoreCorruptionError(RuntimeError):
    """Raised when the cleaned aggregate file cannot be parsed safely."""


@dataclass(frozen=True)
class CleanedStoreSaveResult:
    """Committed cleaned write state that can be rolled back."""

    path: Path
    rollback_token: AtomicWriteRollbackToken


class CleanedStore:
    """Persist cleaned content into one JSON file."""

    def __init__(
        self,
        file_path: str | Path,
        temp_file_path: str | Path | None = None,
        backup_file_path: str | Path | None = None,
    ):
        self.file_path = Path(file_path)
        self.temp_file_path = Path(temp_file_path) if temp_file_path else self.file_path.with_suffix(f"{self.file_path.suffix}.tmp")
        self.backup_file_path = (
            Path(backup_file_path) if backup_file_path else self.file_path.with_suffix(f"{self.file_path.suffix}.bak")
        )
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.temp_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_file_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, title: str, content: str, metadata: dict | None = None) -> Path:
        return self.save_with_rollback(title, content, metadata=metadata).path

    def save_with_rollback(self, title: str, content: str, metadata: dict | None = None) -> CleanedStoreSaveResult:
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

        serialized_records = json.dumps(records, ensure_ascii=False, indent=2)
        rollback_token = self._write_text_atomically(serialized_records)
        return CleanedStoreSaveResult(path=self.file_path, rollback_token=rollback_token)

    def rollback(self, save_result: CleanedStoreSaveResult) -> None:
        if save_result.path != self.file_path:
            raise ValueError(f"Rollback target mismatch: expected {self.file_path}, got {save_result.path}")
        rollback_atomic_write(save_result.rollback_token)

    def _load_records(self) -> list[dict]:
        self._reconcile_temporary_files()

        if not self.file_path.exists():
            return []

        try:
            raw_data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except UnicodeDecodeError as exc:
            raise CleanedStoreCorruptionError(
                f"Cleaned store file {self.file_path} is corrupted: not valid UTF-8 text."
            ) from exc
        except json.JSONDecodeError as exc:
            raise CleanedStoreCorruptionError(self._build_decode_error_message(exc)) from exc

        if not isinstance(raw_data, list):
            raise CleanedStoreCorruptionError(
                f"Cleaned store file {self.file_path} is invalid: expected a JSON array, got {type(raw_data).__name__}."
            )

        for index, record in enumerate(raw_data):
            if not isinstance(record, dict):
                raise CleanedStoreCorruptionError(
                    f"Cleaned store file {self.file_path} is invalid: item {index} must be an object, "
                    f"got {type(record).__name__}."
                )
        return raw_data

    def _write_text_atomically(self, content: str) -> AtomicWriteRollbackToken:
        self._reconcile_temporary_files()
        existed_before = self.file_path.exists()
        try:
            self._write_temp_file(content)

            self._refresh_backup()
            self._replace_file(self.temp_file_path, self.file_path)
        except OSError:
            self._cleanup_temporary_file(self.temp_file_path, raise_on_error=False)
            raise

        return AtomicWriteRollbackToken(
            target_path=self.file_path,
            backup_path=self.backup_file_path,
            existed_before=existed_before,
        )

    def _refresh_backup(self) -> None:
        if not self.file_path.exists():
            return
        self._replace_file(self.file_path, self.backup_file_path, copy_source=True)

    def _write_temp_file(self, content: str) -> None:
        with self.temp_file_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())

    def _reconcile_temporary_files(self) -> None:
        seen_paths: set[Path] = set()
        for temp_path in (self.temp_file_path, destination_temp_path(self.backup_file_path)):
            if temp_path in seen_paths:
                continue
            seen_paths.add(temp_path)
            try:
                self._cleanup_temporary_file(temp_path, raise_on_error=True)
            except OSError as exc:
                raise CleanedStoreCorruptionError(
                    f"Cleaned store temporary files for {self.file_path} are left over and could not be removed safely."
                ) from exc

    def _cleanup_temporary_file(self, path: Path, raise_on_error: bool) -> None:
        if not path.exists():
            return

        try:
            path.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            if not raise_on_error:
                return
            raise CleanedStoreCorruptionError(
                f"Cleaned store temporary files for {self.file_path} are left over and could not be removed safely."
            ) from exc

    def _replace_file(self, source: Path, destination: Path, copy_source: bool = False) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_destination = self._destination_temp_path(destination)
        try:
            if copy_source:
                with source.open("rb") as input_file, temp_destination.open("wb") as output_file:
                    output_file.write(input_file.read())
                    output_file.flush()
                    os.fsync(output_file.fileno())
                os.replace(temp_destination, destination)
            else:
                os.replace(source, destination)
        finally:
            self._cleanup_temporary_file(temp_destination, raise_on_error=False)

    def _destination_temp_path(self, destination: Path) -> Path:
        return destination_temp_path(destination)

    def _build_decode_error_message(self, error: json.JSONDecodeError) -> str:
        backup_note = ""
        if self.backup_file_path.exists():
            backup_note = f" Last known good backup: {self.backup_file_path}."
        return (
            f"Cleaned store file {self.file_path} is corrupted: {error.msg} "
            f"(line {error.lineno}, column {error.colno}, char {error.pos}).{backup_note}"
        )
