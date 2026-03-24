"""Sample script to crawl a few pages for testing."""

import sys
sys.path.insert(0, ".")

from src.crawler.client import MediaWikiClient
from src.parser.wikitext_parser import WikitextParser
from src.cleaner.text_cleaner import TextCleaner
from src.storage.writer import DataManager
from src.utils.config import load_config
from src.utils.logger import setup_logger


def main():
    """Crawl sample pages."""
    config = load_config()
    logger = setup_logger("sample", level="DEBUG")

    client = MediaWikiClient(config)
    parser = WikitextParser()
    cleaner = TextCleaner()
    data_manager = DataManager(config.output_dir)

    # Sample pages to crawl
    sample_pages = [
        "甘雨",
        "钟离",
        "温迪",
        "可莉",
    ]

    for title in sample_pages:
        logger.info(f"Crawling: {title}")

        try:
            pages = list(client.get_page(titles=title))

            for page in pages:
                parsed = parser.parse(page.content_raw)

                page.templates = parsed.get("templates", [])
                page.links = parsed.get("links", [])
                page.infobox = parsed.get("infobox")

                if parsed.get("text"):
                    page.content_clean = cleaner.clean(parsed["text"])
                elif page.content_raw:
                    page.content_clean = cleaner.clean(page.content_raw)

                page.links = cleaner.normalize_links(page.links)
                page.categories = cleaner.normalize_categories(page.categories)

                data_manager.write_all(page)
                logger.info(f"Success: {page.title}")

        except Exception as e:
            logger.error(f"Failed: {title} - {e}")

    data_manager.close()
    logger.info("Done!")


if __name__ == "__main__":
    main()
