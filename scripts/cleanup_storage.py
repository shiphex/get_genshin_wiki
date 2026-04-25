#!/usr/bin/env python3
"""Clean generated crawl artifacts and temporary files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.cleanup import FILE_TYPE_CHOICES, PROJECT_CHOICES, cleanup_paths, collect_cleanup_targets
from src.utils.config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="清理爬虫生成的临时文件和输出文件")
    parser.add_argument(
        "--project",
        dest="projects",
        action="append",
        choices=PROJECT_CHOICES,
        help="选择要清理的文件所属项目，可重复传入",
    )
    parser.add_argument(
        "--type",
        dest="file_types",
        action="append",
        choices=FILE_TYPE_CHOICES,
        help="选择要清理的文件类型，可重复传入",
    )
    parser.add_argument("--include-cache", action="store_true", help="同时清理 __pycache__、.pytest_cache 和 .pyc")
    parser.add_argument("--include-logs", action="store_true", help="同时清理 .log 日志文件")
    parser.add_argument("--dry-run", action="store_true", help="只显示将要清理的文件，不实际删除")
    parser.add_argument("--yes", action="store_true", help="跳过确认提示")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    workspace_root = Path(__file__).parent.parent
    config = load_config()
    targets = collect_cleanup_targets(
        storage_config=config.get("storage", {}),
        projects=args.projects,
        file_types=args.file_types,
        include_cache=args.include_cache,
        include_logs=args.include_logs,
        root_dir=workspace_root,
    )

    if not targets:
        print("没有匹配到可清理的文件。")
        return 0

    print("待清理目标：")
    for target in targets:
        print(f"- {target.relative_to(workspace_root)}")

    if not args.dry_run and not args.yes:
        confirm = input("确认删除这些文件吗？[y/N]: ").strip().lower()
        if confirm not in {"y", "yes"}:
            print("已取消。")
            return 0

    result = cleanup_paths(targets, dry_run=args.dry_run)
    action = "将清理" if args.dry_run else "已清理"
    print(f"{action} {result.removed_count} 个目标。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
