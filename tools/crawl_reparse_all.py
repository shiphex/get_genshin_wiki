from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.reparse_and_store import (
    DEFAULT_DATA_ROOT,
    DEFAULT_ENTITY_ORDER,
    DEFAULT_LIMIT,
    print_report_summary,
    run_batch,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl, reparse, validate, and test wiki data by entity category.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="Root directory used by JsonFileStore.",
    )
    parser.add_argument(
        "--entity",
        dest="entities",
        action="append",
        choices=DEFAULT_ENTITY_ORDER,
        default=None,
        help="Entity id to process. Repeat for multiple entities. Defaults to all entities.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum number of titles to crawl per entity.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = run_batch(
        data_root=args.data_root,
        entity_ids=args.entities,
        limit=args.limit,
        fetch_pages=True,
        include_pytest=True,
    )
    print_report_summary(report)
    pytest_failed = report.get("pytest", {}).get("failed", 0) > 0 or report.get("pytest", {}).get("exit_code", 1) != 0
    return 0 if report["validation"]["failed"] == 0 and not pytest_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
