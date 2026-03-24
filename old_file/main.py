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


def parse_wikitext_template(content: str, template_name: str) -> dict:
    """
    Parse a wikitext template and extract all key=value pairs.
    Uses simple brace counting to handle nested templates.
    """
    import re
    result = {}

    # Find the start of the template - must be followed by |
    # Use pattern: {{template_name|
    start_pattern = r'\{\{' + re.escape(template_name) + r'\s*(\|)'
    start_match = re.search(start_pattern, content)
    if not start_match:
        return result

    # Get position after {{template_name|
    start_pos = start_match.start()
    # Skip whitespace and |
    param_start = start_match.end()
    while param_start < len(content) and content[param_start] in ' \t':
        param_start += 1
    if param_start < len(content) and content[param_start] == '|':
        param_start += 1

    # Find the end by counting braces
    brace_count = 2  # We've seen {{
    pos = param_start
    while pos < len(content) and brace_count > 0:
        if content[pos] == '{':
            brace_count += 1
        elif content[pos] == '}':
            brace_count -= 1
        pos += 1

    # Extract the content between template name and closing }}
    params_text = content[param_start:pos-1]

    # Parse key=value pairs - simple split by | at top level
    current_key = None
    current_value = []
    brace_depth = 0

    for char in params_text:
        if char == '{':
            brace_depth += 1
            current_value.append(char)
        elif char == '}':
            brace_depth -= 1
            current_value.append(char)
        elif char == '|' and brace_depth == 0:
            # New parameter
            if current_key is not None:
                value = ''.join(current_value).strip()
                if value:
                    result[current_key] = value
            current_key = None
            current_value = []
        else:
            current_value.append(char)

        # Check for = at top level when not inside braces
        if char == '=' and brace_depth == 0 and current_key is None and current_value:
            # This is a key= value
            possible_key = ''.join(current_value[:-1]).strip()
            if possible_key:
                current_key = possible_key
                current_value = []

    # Don't forget the last parameter
    if current_key is not None:
        value = ''.join(current_value).strip()
        if value:
            result[current_key] = value

    return result


def get_parsed_sections(client, title: str) -> dict:
    """
    Fetch rendered HTML sections from wiki page using action=parse.
    Returns dict with 剧情相关, 活动相关, 生日贺图 extracted from HTML.
    """
    import requests
    import re

    result = {
        "剧情相关": [],
        "活动相关": [],
        "生日贺图文本": []
    }

    try:
        # Use action=parse to get rendered HTML
        api_url = client.api_url.replace('api.php', 'api.php')
        params = {
            'action': 'parse',
            'format': 'json',
            'page': title,
            'prop': 'text'
        }

        resp = requests.get(api_url, params=params, timeout=30)
        data = resp.json()
        text = data.get('parse', {}).get('text', {}).get('*', '')

        # Extract 剧情相关 - from id to the next section (活动相关 or h3)
        match = re.search(r'id=\"剧情相关\"[^>]*>.*?<h[23][^>]*>(.*?)(?=<h[23][^>]*>(?:活动相关|官方贺图|人物考据)|<span class=\"mw-headline\"[^>]*>)(.*?)', text, re.DOTALL)
        if not match:
            # Try simpler match - from 剧情相关 to 活动相关
            match = re.search(r'id=\"剧情相关\"[^>]*>(.*?)id=\"活动相关\"', text, re.DOTALL)
        if match:
            content = match.group(1)
            # Extract links: <a title="...">text</a>
            links = re.findall(r'<a[^>]*title=\"([^\"]+)\"[^>]*>([^<]+)</a>', content)
            for title_link, name in links:
                if title_link.startswith('编辑') or not title_link:
                    continue
                result["剧情相关"].append(name.strip())

        # Extract 活动相关 - from id to the next section (官方贺图 or 人物考据)
        match = re.search(r'id=\"活动相关\"[^>]*>(.*?)id=\"官方贺图\"', text, re.DOTALL)
        if match:
            content = match.group(1)
            links = re.findall(r'<a[^>]*title=\"([^\"]+)\"[^>]*>([^<]+)</a>', content)
            for title_link, name in links:
                if title_link.startswith('编辑') or not title_link:
                    continue
                result["活动相关"].append(name.strip())

        # Extract 生日贺图 - from id to next section
        match = re.search(r'id=\"官方贺图\"[^>]*>(.*?)id=\"角色宣传视频\"', text, re.DOTALL)
        if match:
            content = match.group(1)
            # Look for images with alt text (birthday greetings)
            birthdays = re.findall(r'alt=\"([^\"]+)\"', content)
            for b in birthdays:
                if b.strip():
                    result["生日贺图"].append(b.strip())

    except Exception as e:
        pass

    return result


def crawl_character_list(
    client: MediaWikiClient,
    parser: WikitextParser,
    cleaner: TextCleaner,
    logger: logging.Logger,
    output_dir: str = "data/character",
    limit: int = None,
) -> int:
    """
    Crawl all characters from the character page.

    Args:
        client: MediaWiki client
        parser: Wikitext parser
        cleaner: Text cleaner
        logger: Logger
        output_dir: Output directory for characters
        limit: Optional limit on number of characters

    Returns:
        Number of characters crawled
    """
    import json
    import re
    from pathlib import Path

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Create subdirectories for raw and cleaned data
    raw_path = output_path / "raw"
    cleaned_path = output_path / "cleaned"
    raw_path.mkdir(parents=True, exist_ok=True)
    cleaned_path.mkdir(parents=True, exist_ok=True)

    characters = []
    count = 0
    failed_count = 0

    logger.info("Starting to crawl characters from category: 角色")

    # Open file for incremental writing
    jsonl_path = output_path / "characters.jsonl"

    # Get all pages in "角色" category
    category_members = client.get_category_members("角色")
    for member in category_members:
        if limit and count >= limit:
            break

        try:
            # Get page content
            pages = list(client.get_page(titles=member.title))

            for page in pages:
                # Save raw wikitext
                raw_file = raw_path / f"{page.title}.txt"
                with open(raw_file, "w", encoding="utf-8") as f:
                    f.write(page.content_raw)

                # Get parsed HTML sections for 剧情相关 and 活动相关
                parsed_sections = get_parsed_sections(client, page.title)

                content = page.content_raw

                # Parse templates properly
                role_data = parse_wikitext_template(content, "角色")
                info_data = parse_wikitext_template(content, "角色/信息")
                story_data = parse_wikitext_template(content, "角色/故事")
                constellation_data = parse_wikitext_template(content, "角色/命之座")

                # Map fields according to request_character.md requirements
                # 基础信息
                # Note: "神之眼/三相月临/月之轮/古龙大权/神之心/其他" field comes from 角色/故事 template
                神之眼相关 = story_data.get("神之眼", "")
                基础信息 = {
                    "称号": role_data.get("称号", ""),
                    "全名": role_data.get("全名", role_data.get("名称", "")),
                    "英文名称": role_data.get("英文名称", ""),
                    "所属地区": role_data.get("所属", ""),
                    "出身": role_data.get("出身", ""),
                    "种族": role_data.get("种族", ""),
                    "性别": role_data.get("性别", ""),
                    "稀有度": role_data.get("稀有度", ""),
                    "限定": role_data.get("限定", ""),
                    "神之眼/三相月临/月之轮/古龙大权/神之心/其他": 神之眼相关,
                    "元素属性": role_data.get("元素属性", ""),
                    "武器类型": role_data.get("武器类型", ""),
                    "羁绊属性": role_data.get("羁绊属性", ""),
                    "命之座": role_data.get("命之座", ""),
                    "特殊料理": role_data.get("特殊料理", ""),
                    "实装日期": role_data.get("实装日期", ""),
                    "实装版本": role_data.get("实装版本", ""),
                    "TAG": role_data.get("TAG", ""),
                    "介绍": role_data.get("介绍", ""),
                    "祈愿类型": role_data.get("祈愿类型", ""),
                }

                # 其他信息
                其他信息 = {
                    "昵称/外号": info_data.get("昵称/外号", ""),
                    "所属": info_data.get("归属", ""),
                    "职业": info_data.get("职业", ""),
                    "生日": info_data.get("生日", ""),
                    "体型": info_data.get("体型", ""),
                    "卡池名": info_data.get("卡池名", ""),
                    "个人任务": info_data.get("个人任务", ""),
                    "名片名称": info_data.get("名片名称", ""),
                    "名片描述": info_data.get("名片描述", ""),
                }

                # 角色故事 - collect 角色详细, 角色故事1-6, 冒险笔记, etc.
                角色故事 = []
                if story_data.get("角色详细"):
                    角色故事.append({
                        "title": "角色详细",
                        "content": story_data.get("角色详细", "")
                    })
                for i in range(1, 7):
                    key = f"角色故事{i}"
                    if story_data.get(key):
                        角色故事.append({
                            "title": key,
                            "content": story_data.get(key, "")
                        })
                # Check for special stories (冒险笔记, etc.)
                if story_data.get("冒险笔记"):
                    角色故事.append({
                        "title": "冒险笔记",
                        "content": story_data.get("冒险笔记", "")
                    })
                if story_data.get("神之眼"):
                    角色故事.append({
                        "title": "神之眼",
                        "content": story_data.get("神之眼", "")
                    })

                # 命之座
                命之座 = []
                for i in range(1, 7):
                    const_key = f"命之座{i}"
                    const_effect_key = f"命之座{i}效果"
                    if constellation_data.get(const_key):
                        命之座.append({
                            "name": constellation_data.get(const_key, ""),
                            "effect": constellation_data.get(const_effect_key, "")
                        })

                # Extract 角色相关 sections from raw content first
                # Need to extract wiki links properly

                角色相关 = {
                    "壹_人物": "",
                    "贰_故事": "",
                    "剧情相关": [],
                    "活动相关": [],
                    "生日贺图文本": [],
                    "人物考据": ""
                }

                # Extract from raw content first to get wiki links
                # Extract 壹·人物
                match = re.search(r'壹·人物\s*(.+?)(?=贰|·|$)', content, re.DOTALL)
                if match:
                    raw_text = match.group(1)
                    # Clean wiki markup
                    cleaned_text = cleaner.clean(raw_text)
                    角色相关["壹_人物"] = cleaned_text.strip()

                # Extract 贰·故事
                match = re.search(r'贰·故事\s*(.+?)(?=剧情|·|$)', content, re.DOTALL)
                if match:
                    raw_text = match.group(1)
                    cleaned_text = cleaner.clean(raw_text)
                    角色相关["贰_故事"] = cleaned_text.strip()

                # Extract 剧情相关 - keep full context like [[白垩之章]]·第一幕「...」
                match = re.search(r'剧情相关===\s*(.+?)===\s*活动相关', content, re.DOTALL)
                if match:
                    raw_text = match.group(1).strip()
                    # Replace <br> with newline
                    raw_text = raw_text.replace('<br>', '\n')
                    # Split by lines - each line is a complete story reference
                    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                    剧情相关_list = []
                    for line in lines:
                        # Remove wiki link markers but keep full text
                        # Replace [[link]] with link text, keep the rest
                        cleaned_line = re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', r'\2\1', line)
                        if cleaned_line:
                            剧情相关_list.append(cleaned_line.strip())
                # Use parsed_sections for 剧情相关 and 活动相关
                if parsed_sections.get("剧情相关"):
                    角色相关["剧情相关"] = parsed_sections["剧情相关"]
                else:
                    # Fallback to wikitext extraction
                    match = re.search(r'剧情相关===\s*(.+?)===\s*活动相关', content, re.DOTALL)
                    if match:
                        raw_text = match.group(1).strip()
                        raw_text = raw_text.replace('<br>', '\n')
                        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                        剧情相关_list = []
                        for line in lines:
                            cleaned_line = re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', r'\2\1', line)
                            if cleaned_line:
                                剧情相关_list.append(cleaned_line.strip())
                        角色相关["剧情相关"] = 剧情相关_list

                # Extract 活动相关 from parsed HTML
                if parsed_sections.get("活动相关"):
                    角色相关["活动相关"] = parsed_sections["活动相关"]
                else:
                    # Fallback to wikitext extraction
                    match = re.search(r'活动相关===\s*(.+?)===官方贺图', content, re.DOTALL)
                if match:
                    raw_text = match.group(1).strip()
                    # Replace <br> with newline
                    raw_text = raw_text.replace('<br>', '\n')
                    # Split by lines - each line is a complete event reference
                    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                    活动相关_list = []
                    for line in lines:
                        # Remove wiki link markers but keep full text
                        cleaned_line = re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', r'\2\1', line)
                        if cleaned_line:
                            活动相关_list.append(cleaned_line.strip())
                    角色相关["活动相关"] = 活动相关_list

                # Extract 人物考据
                match = re.search(r'人物考据\s*(.+?)$', content, re.DOTALL)
                if match:
                    raw_text = match.group(1)
                    cleaned_text = cleaner.clean(raw_text)
                    角色相关["人物考据"] = cleaned_text.strip()

                # Extract 生日贺图 from parsed HTML
                if parsed_sections.get("生日贺图"):
                    角色相关["生日贺图"] = parsed_sections["生日贺图"]

                # Fetch voice data from voice page (e.g., 阿贝多语音)
                voice_data = {}
                try:
                    voice_page_title = f"{page.title}语音"
                    voice_pages = list(client.get_page(titles=voice_page_title))
                    if voice_pages:
                        voice_content = voice_pages[0].content_raw
                        # Extract voice lines from the content
                        # Look for sections like "==xxx=="
                        sections = re.split(r'==+', voice_content)
                        current_category = ""
                        for i, section in enumerate(sections):
                            if not section.strip():
                                continue
                            # First section is usually empty or intro
                            if i == 0:
                                continue
                            # Check if this is a section header (followed by content)
                            lines = section.split('\n')
                            if lines:
                                section_name = lines[0].strip()
                                if section_name:
                                    current_category = section_name
                                    if current_category not in voice_data:
                                        voice_data[current_category] = []
                                    # Rest is content
                                    content_lines = '\n'.join(lines[1:]).strip()
                                    if content_lines:
                                        voice_data[current_category].append(content_lines)
                except Exception as e:
                    logger.warning(f"Failed to fetch voice data for {page.title}: {e}")

                # Build final structured data
                character_data = {
                    "title": page.title,
                    "url": page.url,
                    "data": {
                        "基础信息": 基础信息,
                        "其他信息": 其他信息,
                        "角色故事": 角色故事,
                        "命之座": 命之座,
                        "角色相关": 角色相关,
                        "voice": voice_data
                    },
                    "raw": {
                        "templates": {},
                        "links": []
                    }
                }

                characters.append(character_data)
                count += 1

                # Incrementally save to JSONL
                with open(jsonl_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(character_data, ensure_ascii=False) + "\n")

                logger.info(f"Crawled character: {page.title} ({count} characters)")

        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to crawl {member.title}: {e}")
            continue

    # Save complete character list as JSON
    json_path = output_path / "characters.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(characters, f, ensure_ascii=False, indent=2)

    logger.info(f"Finished crawling characters: {count} characters saved, {failed_count} failed to {output_dir}")
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
    parser.add_argument(
        "--character-list",
        "-cl",
        action="store_true",
        help="Crawl all characters from the character list",
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

        elif args.character_list:
            # Crawl character list
            count = crawl_character_list(
                client,
                wiki_parser,
                cleaner,
                logger,
                output_dir="data/character",
                limit=args.limit,
            )
            logger.info(f"Crawled {count} characters")

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
