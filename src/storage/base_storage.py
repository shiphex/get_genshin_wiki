"""Shared storage assembly for namespace writers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .cleaned_store import CleanedStore
from .failure_store import FailureStore
from .layout import StorageLayout, build_storage_layout, resolve_legacy_namespace_dirs
from .manifest_store import ManifestStore
from .raw_store import RawStore
from .record_store import RecordStore

logger = logging.getLogger(__name__)


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
        self.cleaned_store = CleanedStore(self.layout.cleaned_file)
        self.record_store = RecordStore(self.layout.structured_file, legacy_paths=legacy_structured_paths)
        self.failure_store = FailureStore(self.layout.failed_file, legacy_paths=legacy_failed_paths)
        self.manifest_store = ManifestStore(self.layout.manifests_dir)

    def build_clean_text(self, record) -> str:
        raise NotImplementedError

    def save(self, record, raw_html: str, structured: dict[str, Any]) -> None:
        self.record_store.append(structured)
        if raw_html:
            self.raw_store.save(record.title, raw_html, suffix=".html")
        self.cleaned_store.save(record.title, self.build_clean_text(record), metadata=structured)
        logger.info("已保存 %s: %s", self.namespace, record.title)

    def save_failed(self, title: str, reason: str) -> None:
        self.failure_store.append(title, reason)

    def load_saved_titles(self) -> set[str]:
        return self.record_store.load_titles()

    def load_failed_titles(self) -> set[str]:
        return self.failure_store.load_titles()

    def save_manifest(self, manifest: dict[str, Any], run_id: str) -> Path:
        return self.manifest_store.save(manifest, run_id)
