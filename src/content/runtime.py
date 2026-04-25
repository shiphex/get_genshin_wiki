"""Shared crawl runtime."""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from src.alerts.reporter import AlertReporter
from src.alerts.rules import empty_list_page, writer_failure
from src.content.base import CrawlRunResult
from src.content.registry import get_content_spec
from src.crawler.client import MediaWikiClient

logger = logging.getLogger(__name__)


def _snapshot_config(config: dict[str, Any]) -> dict[str, Any]:
    snapshot = deepcopy(config)
    storage_cfg = snapshot.get("storage", {})
    keep_keys = ["output_dir", "books_dir", "arms_dir", "artifacts_dir", "links_dir", "book_dir", "arm_dir", "artifact_dir"]
    snapshot["storage"] = {key: storage_cfg[key] for key in keep_keys if key in storage_cfg}
    return snapshot


def _record_to_dict(record: Any) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        return record.to_dict()
    if is_dataclass(record):
        return asdict(record)
    if isinstance(record, dict):
        return record
    raise TypeError(f"Unsupported record type: {type(record)!r}")


def create_mediawiki_client(config: dict[str, Any]) -> MediaWikiClient:
    mw_config = config["mediawiki"]
    return MediaWikiClient(
        api_url=mw_config["api_url"],
        base_url=mw_config["base_url"],
        request_interval=mw_config.get("request_interval", 3),
        timeout=mw_config.get("timeout", 30),
        max_retries=mw_config.get("max_retries", 3),
        user_agent=mw_config.get("user_agent", "get_wiki_genshin/0.1.0"),
    )


def run_crawl(namespace: str, config: dict[str, Any], client: MediaWikiClient | None = None) -> CrawlRunResult:
    """Run crawl flow for a single namespace."""
    spec = get_content_spec(namespace)
    client = client or create_mediawiki_client(config)
    parser = spec.create_parser(client.base_url)
    validator = spec.create_validator()
    writer = spec.create_writer(config.get("storage", {}))
    reporter = AlertReporter(writer.layout.alerts_dir)

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    started_at = datetime.now().isoformat()

    logger.info("获取 %s 列表页: %s", namespace, spec.page_title)
    links = spec.extract_links(parser, client.get_page_html(spec.page_title))
    if not links:
        reporter.add(empty_list_page(namespace, spec.page_title))

    saved_titles = writer.load_saved_titles()
    failed_titles = writer.load_failed_titles()
    pending_links = [link for link in links if link["title"] not in saved_titles and link["title"] not in failed_titles]

    saved_count = 0
    failed_count = 0
    for link in pending_links:
        title = link["title"]
        try:
            logger.info("爬取 %s: %s", namespace, title)
            detail_html = client.get_page_html(title)
            record = spec.parse_detail(parser, detail_html, title, link["url"])
            if hasattr(record, "fetched_at"):
                record.fetched_at = datetime.now().isoformat()
            reporter.extend(validator.validate(record))
            writer.save(record=record, raw_html=detail_html, structured=_record_to_dict(record))
            saved_count += 1
        except Exception as exc:
            failed_count += 1
            writer.save_failed(title, str(exc))
            reporter.add(writer_failure(namespace, title, str(exc)))

    manifest = {
        "run_id": run_id,
        "namespace": namespace,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
        "source_page": spec.page_title,
        "fetched_count": len(pending_links),
        "saved_count": saved_count,
        "failed_count": failed_count,
        "warning_count": reporter.count("warning"),
        "parser_version": "v1",
        "config_snapshot": _snapshot_config(config),
    }
    manifest_path = writer.save_manifest(manifest, run_id)
    alerts_path = reporter.save(run_id)
    return CrawlRunResult(namespace=namespace, manifest=manifest, manifest_path=manifest_path, alerts_path=alerts_path)
