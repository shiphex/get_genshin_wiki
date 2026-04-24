#!/usr/bin/env python3
"""链接更新检查器 CLI"""
import argparse
import logging
import subprocess
import sys
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawler.client import MediaWikiClient
from src.linkchecker import LinkChecker
from src.utils.config import load_config
from src.utils.logger import setup_logging

logger = logging.getLogger(__name__)

# 内容类型对应的爬虫脚本
CRAWL_SCRIPTS = {
    "arms": "scripts/crawl_arms.py",
    "books": "scripts/crawl_books.py",
    "artifacts": "scripts/crawl_artifacts.py",
}


def print_comparison_result(result, content_type: str, as_json: bool = False) -> None:
    """打印比较结果"""
    if as_json:
        import json
        output = {
            "content_type": content_type,
            "new_count": len(result.new_links),
            "removed_count": len(result.removed_links),
            "unchanged_count": len(result.unchanged),
            "has_updates": result.has_updates,
            "new_links": [link.to_dict() for link in result.new_links],
            "removed_links": [link.to_dict() for link in result.removed_links],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print("=" * 50)
        print(f"链接更新检查: {content_type}")
        print("=" * 50)
        print(f"新增链接: {len(result.new_links)}")
        if result.new_links:
            for link in result.new_links[:10]:
                print(f"  + {link.title}")
            if len(result.new_links) > 10:
                print(f"  ... 还有 {len(result.new_links) - 10} 个")
        print(f"已删除链接: {len(result.removed_links)}")
        if result.removed_links:
            for link in result.removed_links[:10]:
                print(f"  - {link.title}")
            if len(result.removed_links) > 10:
                print(f"  ... 还有 {len(result.removed_links) - 10} 个")
        print(f"未变化链接: {len(result.unchanged)}")
        print()

        if result.has_updates:
            print("有可用更新。")
        else:
            print("没有可用更新。")


def confirm_deletion(removed_count: int) -> bool:
    """确认删除操作

    Args:
        removed_count: 即将删除的链接数量

    Returns:
        bool: 是否确认删除
    """
    print()
    print(f"警告: 将从本地存储中移除 {removed_count} 个链接。")
    print("这些项目可能在 Wiki 上已被弃用或重命名。")
    print()
    response = input("确认删除？[y/N]: ").strip().lower()
    return response == "y"


def trigger_crawl(content_type: str) -> bool:
    """触发爬虫爬取新项目

    Args:
        content_type: 内容类型

    Returns:
        bool: 是否成功
    """
    script = CRAWL_SCRIPTS.get(content_type)
    if not script:
        logger.error(f"未知内容类型: {content_type}")
        return False

    script_path = Path(__file__).parent.parent / script
    if not script_path.exists():
        logger.error(f"爬虫脚本不存在: {script_path}")
        return False

    logger.info(f"触发爬虫: {script}")
    try:
        subprocess.run([sys.executable, str(script_path)], check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"爬虫执行失败: {e}")
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="原神 Wiki 链接更新检查器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                              # 检查武器（默认）
  %(prog)s --type books                # 检查书籍
  %(prog)s --type artifacts --check-only  # 仅检查圣遗物（不修改）
  %(prog)s --type arms --update         # 更新武器链接
  %(prog)s --type arms --update --yes   # 更新武器链接（自动确认删除）
  %(prog)s --type arms --update --crawl-new  # 更新并爬取新武器
  %(prog)s --json                       # JSON 格式输出
        """
    )

    parser.add_argument(
        "--type",
        choices=["arms", "books", "artifacts"],
        default="arms",
        help="内容类型（默认: arms）"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="仅检查更新，不修改文件"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="更新本地链接文件"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="自动确认删除"
    )
    parser.add_argument(
        "--crawl-new",
        action="store_true",
        help="更新后触发爬虫"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出"
    )

    args = parser.parse_args()

    # 设置日志
    setup_logging()
    logger.info("=" * 50)
    logger.info("开始链接更新检查")
    logger.info("=" * 50)

    # 加载配置
    config = load_config()
    mw_config = config["mediawiki"]
    storage_config = config.get("storage", {})

    # 初始化 MediaWiki 客户端
    client = MediaWikiClient(
        api_url=mw_config["api_url"],
        base_url=mw_config["base_url"],
        request_interval=mw_config.get("request_interval", 3),
        timeout=mw_config.get("timeout", 30),
        max_retries=mw_config.get("max_retries", 3),
        user_agent=mw_config.get("user_agent", "get_wiki_genshin/0.1.0"),
    )

    # 初始化链接检查器
    links_dir = Path(storage_config.get("links_dir", "storage/links"))
    checker = LinkChecker(
        content_type=args.type,
        links_dir=links_dir,
        client=client,
    )

    # 检查更新
    result = checker.check_for_updates()

    # 打印结果
    print_comparison_result(result, args.type, args.json)

    # 如果是仅检查模式，直接返回
    if args.check_only:
        return

    # 更新链接文件
    if args.update:
        keep_removed = False

        # 如果有删除项，需要确认
        if result.removed_links and not args.yes:
            if not confirm_deletion(len(result.removed_links)):
                print("已取消更新。")
                return
            keep_removed = False
        elif args.yes:
            keep_removed = False
        else:
            keep_removed = True  # 没有删除项时保留

        # 更新链接
        checker.update_links(result, keep_removed=keep_removed)
        print(f"已更新: {checker.link_file}")

        # 如果需要，触发爬虫
        if args.crawl_new and result.new_links:
            print()
            print(f"开始爬取 {len(result.new_links)} 个新项目...")
            if trigger_crawl(args.type):
                print("爬取完成。")
            else:
                print("爬取过程中出现问题。")

    logger.info("=" * 50)
    logger.info("检查完成")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()