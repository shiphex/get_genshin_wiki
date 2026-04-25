"""Shared storage assembly for namespace writers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .atomic_write import atomic_append_text, atomic_write_text, rollback_atomic_write
from .cleaned_store import CleanedStore
from .failure_store import FailureStore
from .layout import StorageLayout, build_storage_layout, resolve_legacy_namespace_dirs, sanitize_filename
from .manifest_store import ManifestStore
from .raw_store import RawStore
from .record_store import RecordStore

logger = logging.getLogger(__name__)


class StorageTransactionRollbackError(RuntimeError):
    """Raised when a transactional save fails and rollback cannot complete."""


class BaseNamespaceStorage:
    """Compose raw/cleaned/structured stores for one namespace."""

    namespace = ""

    def __init__(self, storage_config: dict[str, Any] | None = None, base_dir: str | None = None):
        self.storage_config = storage_config or {}
        self.layout: StorageLayout = build_storage_layout(
            storage_config=self.storage_config,
            namespace=self.namespace,
            base_dir=base_dir,
        )
        legacy_roots = [self.layout.base_dir, *resolve_legacy_namespace_dirs(self.storage_config, self.namespace, base_dir=base_dir)]
        legacy_structured_paths = [root / f"{self.namespace}.jsonl" for root in legacy_roots]
        legacy_structured_paths.extend(root / "structured" / f"{self.namespace}.jsonl" for root in legacy_roots[1:])
        legacy_failed_paths = [root / f"failed_{self.namespace}.txt" for root in legacy_roots]
        legacy_failed_paths.extend(root / "failed" / f"failed_{self.namespace}.txt" for root in legacy_roots[1:])
        self.raw_store = RawStore(self.layout.raw_dir)
        self.cleaned_store = CleanedStore(
            self.layout.cleaned_file,
            temp_file_path=self.layout.cleaned_temp_file,
            backup_file_path=self.layout.cleaned_backup_file,
        )
        self.record_store = RecordStore(self.layout.structured_file, legacy_paths=legacy_structured_paths)
        self.failure_store = FailureStore(self.layout.failed_file, legacy_paths=legacy_failed_paths)
        self.manifest_store = ManifestStore(self.layout.manifests_dir)

    def build_clean_text(self, record) -> str:
        raise NotImplementedError

    def save(self, record, raw_html: str, structured: dict[str, Any]) -> None:
        cleaned_result = self.cleaned_store.save_with_rollback(
            record.title,
            self.build_clean_text(record),
            metadata=structured,
        )
        record_token = None

        try:
            record_token = atomic_append_text(
                self.record_store.file_path,
                json.dumps(structured, ensure_ascii=False) + "\n",
                temp_file_path=self.record_store.file_path.with_suffix(f"{self.record_store.file_path.suffix}.tmp"),
                backup_file_path=self.record_store.file_path.with_suffix(f"{self.record_store.file_path.suffix}.bak"),
            )

            if raw_html:
                raw_path = self.raw_store.output_dir / f"{sanitize_filename(record.title)}.html"
                atomic_write_text(
                    raw_path,
                    raw_html,
                    temp_file_path=raw_path.with_suffix(f"{raw_path.suffix}.tmp"),
                    backup_file_path=raw_path.with_suffix(f"{raw_path.suffix}.bak"),
                )
        except (OSError, TypeError, ValueError) as write_error:
            rollback_errors: list[str] = []

            if record_token is not None:
                try:
                    rollback_atomic_write(record_token)
                except (FileNotFoundError, OSError) as rollback_error:
                    rollback_errors.append(f"record_store rollback failed: {rollback_error}")

            try:
                self.cleaned_store.rollback(cleaned_result)
            except (FileNotFoundError, OSError, ValueError) as rollback_error:
                rollback_errors.append(f"cleaned_store rollback failed: {rollback_error}")

            if rollback_errors:
                details = "; ".join(rollback_errors)
                raise StorageTransactionRollbackError(
                    f"Failed to save {self.namespace}:{record.title}. Write error: {write_error}. Rollback error: {details}"
                ) from write_error
            raise
        logger.info("已保存 %s: %s", self.namespace, record.title)

    def save_failed(self, title: str, reason: str) -> None:
        self.failure_store.append(title, reason)

    def load_saved_titles(self) -> set[str]:
        return self.record_store.load_titles()

    def load_failed_titles(self) -> set[str]:
        return self.failure_store.load_titles()

    def save_manifest(self, manifest: dict[str, Any], run_id: str) -> Path:
        return self.manifest_store.save(manifest, run_id)
