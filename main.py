"""Main entry point for Genshin Wiki crawler."""

import argparse
import logging
import sys
from pathlib import Path

from src.crawler.client import MediaWikiClient
from src.parser.wikitext_parser import WikitextParser
from src.cleaner.text_cleaner import TextCleaner
from src.storage.writer import DataManager
from src.utils.config import load_config
from src.utils.logger import setup_logger


def crawl_category(
    client: MediaWikiClient,
    category: str,
    data_manager: DataManager,
    parser: WikitextParser,
    cleaner: TextCleaner,
    logger: logging.Logger,
    limit: int = None,
) -> int:
    """
    Crawl all pages in a category.

    Args:
        client: MediaWiki client
        category: Category name
        data_manager: Data manager
        parser: Wikitext parser
        cleaner: Text cleaner
        logger: Logger
        limit: Optional limit on number of pages

    Returns:
        Number of pages crawled
    """
    count = 0

    logger.info(f"Starting to crawl category: {category}")

    for member in client.get_category_members(category):
        if limit and count >= limit:
            break

        try:
            # Get page content
            pages = list(client.get_page(titles=member.title))

            for page in pages:
                # Parse wikitext
                parsed = parser.parse(page.content_raw)

                # Update page with parsed data
                page.templates = parsed.get("templates", [])
                page.links = parsed.get("links", [])
                # Categories from API already include page categories
                # parsed categories would be from wikitext

                # Extract infobox
                page.infobox = parsed.get("infobox")

                # Clean content
                if parsed.get("text"):
                    page.content_clean = cleaner.clean(parsed["text"])
                elif page.content_raw:
                    page.content_clean = cleaner.clean(page.content_raw)

                # Normalize links and categories
                page.links = cleaner.normalize_links(page.links)
                page.categories = cleaner.normalize_categories(page.categories)

                # Save to all storage
                data_manager.write_all(page)

                count += 1
                logger.info(f"Crawled: {page.title} ({count} pages)")

        except Exception as e:
            logger.error(f"Failed to crawl {member.title}: {e}")
            continue

    logger.info(f"Finished crawling {category}: {count} pages")
    return count


def crawl_page(
    client: MediaWikiClient,
    title: str,
    data_manager: DataManager,
    parser: WikitextParser,
    cleaner: TextCleaner,
    logger: logging.Logger,
) -> bool:
    """
    Crawl a single page.

    Args:
        client: MediaWiki client
        title: Page title
        data_manager: Data manager
        parser: Wikitext parser
        cleaner: Text cleaner
        logger: Logger

    Returns:
        True if successful
    """
    try:
        pages = list(client.get_page(titles=title))

        for page in pages:
            # Parse wikitext
            parsed = parser.parse(page.content_raw)

            # Update page with parsed data
            page.templates = parsed.get("templates", [])
            page.links = parsed.get("links", [])
            page.infobox = parsed.get("infobox")

            # Clean content
            if parsed.get("text"):
                page.content_clean = cleaner.clean(parsed["text"])
            elif page.content_raw:
                page.content_clean = cleaner.clean(page.content_raw)

            # Normalize
            page.links = cleaner.normalize_links(page.links)
            page.categories = cleaner.normalize_categories(page.categories)

            # Save
            data_manager.write_all(page)

            logger.info(f"Crawled: {page.title}")
            return True

        logger.warning(f"Page not found: {title}")
        return False

    except Exception as e:
        logger.error(f"Failed to crawl {title}: {e}")
        return False


def list_categories(
    client: MediaWikiClient,
    limit: int = 100,
) -> list:
    """
    List available categories.

    Args:
        client: MediaWiki client
        limit: Maximum number to list

    Returns:
        List of category names
    """
    categories = []
    for cat in client.get_all_categories(limit=limit):
        categories.append(cat)
    return categories


def crawl_book_list(
    client: MediaWikiClient,
    parser: WikitextParser,
    cleaner: TextCleaner,
    logger: logging.Logger,
    output_dir: str = "data/book",
    limit: int = None,
) -> int:
    """
    Crawl all books from the book list page.

    Args:
        client: MediaWiki client
        parser: Wikitext parser
        cleaner: Text cleaner
        logger: Logger
        output_dir: Output directory for books
        limit: Optional limit on number of books

    Returns:
        Number of books crawled
    """
    import json
    from pathlib import Path

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    books = []
    count = 0
    failed_count = 0

    logger.info("Starting to crawl books from category: 书籍")

    # Open files for incremental writing
    jsonl_path = output_path / "books.jsonl"

    # Get all pages in "书籍" category
    category_members = client.get_category_members("书籍")
    for member in category_members:
        if limit and count >= limit:
            break

        try:
            # Get page content
            pages = list(client.get_page(titles=member.title))

            for page in pages:
                # Parse wikitext
                parsed = parser.parse(page.content_raw)

                # Extract book data
                infobox = parsed.get("infobox")
                book_data = {
                    "title": page.title,
                    "url": page.url,
                    "templates": parsed.get("templates", []),
                    "links": parsed.get("links", []),
                    "infobox": infobox.to_dict() if infobox else {},
                }

                # Clean content
                if parsed.get("text"):
                    book_data["content_clean"] = cleaner.clean(parsed["text"])
                elif page.content_raw:
                    book_data["content_clean"] = cleaner.clean(page.content_raw)

                # Normalize links
                book_data["links"] = cleaner.normalize_links(book_data["links"])

                books.append(book_data)
                count += 1
                # Incrementally save to JSONL after each successful crawl
                with open(jsonl_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(book_data, ensure_ascii=False) + "\n")
                logger.info(f"Crawled book: {page.title} ({count} books)")

        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to crawl {member.title}: {e}")
            continue

    # Save complete books list as JSON
    json_path = output_path / "books.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, indent=2)

    logger.info(f"Finished crawling books: {count} books saved, {failed_count} failed to {output_dir}")
    return count


def main():
    """Main entry point."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Genshin Wiki Crawler")
    parser.add_argument(
        "--config",
        "-c",
        help="Path to config file",
        default="configs/config.yaml",
    )
    parser.add_argument(
        "--category",
        "-cat",
        help="Category to crawl",
    )
    parser.add_argument(
        "--page",
        "-p",
        help="Single page to crawl",
    )
    parser.add_argument(
        "--list-categories",
        "-lc",
        action="store_true",
        help="List available categories",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        help="Limit number of pages to crawl",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--book-list",
        "-bl",
        action="store_true",
        help="Crawl all books from the book list",
    )

    args = parser.parse_args()

    # Load configuration
    config_path = args.config
    if not Path(config_path).exists():
        config_path = None

    config = load_config(config_path)

    # Setup logging
    log_level = "DEBUG" if args.debug else config.log_level
    logger = setup_logger(
        "genshin_wiki",
        level=log_level,
        log_file=config.log_file,
    )

    logger.info("Starting Genshin Wiki Crawler")

    # Initialize components
    client = MediaWikiClient(config)
    wiki_parser = WikitextParser()
    cleaner = TextCleaner()
    data_manager = DataManager(config.output_dir)

    try:
        if args.list_categories:
            # List categories
            categories = list_categories(client, limit=args.limit or 100)
            print("Available categories:")
            for cat in categories:
                print(f"  - {cat}")

        elif args.category:
            # Crawl category
            count = crawl_category(
                client,
                args.category,
                data_manager,
                wiki_parser,
                cleaner,
                logger,
                limit=args.limit,
            )
            logger.info(f"Crawled {count} pages from category {args.category}")

        elif args.book_list:
            # Crawl book list
            count = crawl_book_list(
                client,
                wiki_parser,
                cleaner,
                logger,
                output_dir="data/book",
                limit=args.limit,
            )
            logger.info(f"Crawled {count} books")

        elif args.page:
            # Crawl single page
            success = crawl_page(
                client,
                args.page,
                data_manager,
                wiki_parser,
                cleaner,
                logger,
            )
            if success:
                logger.info(f"Successfully crawled page: {args.page}")
                sys.exit(0)
            else:
                logger.error(f"Failed to crawl page: {args.page}")
                sys.exit(1)

        else:
            parser.print_help()
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

    finally:
        data_manager.close()
        logger.info("Crawler finished")


if __name__ == "__main__":
    main()
