"""书籍页面 HTML 解析器"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class BookVolume:
    title: str
    content: str = ""
    obtain_method: Optional[str] = None


@dataclass
class BookInfo:
    name: str = ""
    volumes_count: int | str = 0
    rarity: str = ""
    genre: str = ""
    country: str = ""
    version: str = ""
    gallery: str = ""
    related_characters: list = field(default_factory=list)
    obtain_method: str = ""
    _obtain_methods: dict = field(default_factory=dict)


@dataclass
class Book:
    title: str
    url: str = ""
    fetched_at: str = ""
    info: BookInfo = field(default_factory=BookInfo)
    volumes: list[BookVolume] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "fetched_at": self.fetched_at,
            "info": {
                "名称": self.info.name,
                "卷数": self.info.volumes_count,
                "稀有度": self.info.rarity,
                "体裁": self.info.genre,
                "国家": self.info.country,
                "实装版本": self.info.version,
                "图鉴": self.info.gallery,
                "相关角色": self.info.related_characters,
                "获取方式": self.info.obtain_method,
            },
            "volumes": [
                {
                    "title": volume.title,
                    "content": volume.content,
                    "obtain_method": volume.obtain_method,
                }
                for volume in self.volumes
            ],
        }


class BookParser:
    """书籍页面 HTML 解析器"""

    def __init__(self, base_url: str = "https://wiki.biligame.com/ys/"):
        self.base_url = base_url

    def parse_book_page(self, html: str, title: str, url: str = "") -> Book:
        soup = BeautifulSoup(html, "html.parser")
        book = Book(title=title, url=url)
        self._parse_infobox(soup, book)
        self._parse_volumes(soup, book)
        return book

    def _parse_infobox(self, soup: BeautifulSoup, book: Book) -> None:
        infobox_table = soup.find("table", class_="wikitable")
        if not infobox_table:
            logger.warning("未找到 Infobox: %s", book.title)
            return

        obtain_methods = {}
        current_volume_title = None
        for row in infobox_table.find_all("tr"):
            header = row.find("th")
            data = row.find("td")

            if header and header.get("colspan") == "2":
                header_text = header.get_text(strip=True)
                if "获取方式" in header_text:
                    continue
                if header_text:
                    current_volume_title = header_text
                    obtain_methods.setdefault(current_volume_title, None)

            if data and current_volume_title:
                data_text = data.get_text(strip=True)
                if data_text and "获取方式" not in data_text:
                    obtain_methods[current_volume_title] = data_text
                    current_volume_title = None

            if header and data and header.get("colspan") != "2":
                key = header.get_text(strip=True)
                value = data.get_text(strip=True)
                if key in ["名称", "名称/外文名称"]:
                    book.info.name = value
                elif key == "卷数":
                    book.info.volumes_count = value
                elif key == "稀有度":
                    img = data.find("img")
                    book.info.rarity = img.get("alt", "").replace(".png", "") if img and img.get("alt") else value
                elif key in ["体裁", "类型"]:
                    book.info.genre = value
                elif key == "国家":
                    book.info.country = value
                elif key in ["実装版本", "实装版本"]:
                    book.info.version = value
                elif key in ["图鉴", "画廊"]:
                    book.info.gallery = value
                elif key in ["相关角色", "角色"]:
                    characters = []
                    for link in data.find_all("a"):
                        if link.get("href", "").startswith("/ys/"):
                            text = link.get_text(strip=True)
                            if text:
                                characters.append(text)
                    book.info.related_characters = list(dict.fromkeys(characters))

        book.info._obtain_methods = obtain_methods
        if not book.info.name:
            book.info.name = book.title

    def _parse_volumes(self, soup: BeautifulSoup, book: Book) -> None:
        obtain_methods = getattr(book.info, "_obtain_methods", {})
        for headline in soup.find_all("span", class_="mw-headline"):
            volume_title = headline.get_text(strip=True)
            if not volume_title:
                continue
            if any(keyword in volume_title for keyword in ["目录", "导航", "参见", "注释", "参考资料", "外部链接"]):
                continue

            current = headline.find_parent("h2")
            if not current:
                continue

            content_parts = []
            for sibling in current.find_next_siblings():
                if sibling.name == "h2":
                    break
                if sibling.name == "p":
                    text = self._get_paragraph_text(sibling)
                    if text:
                        content_parts.append(text)

            book.volumes.append(
                BookVolume(
                    title=volume_title,
                    content="\n\n".join(content_parts),
                    obtain_method=obtain_methods.get(volume_title),
                )
            )

        if book.volumes:
            method_parts = [
                f"{volume.title}: {volume.obtain_method}"
                for volume in book.volumes
                if volume.obtain_method
            ]
            if method_parts:
                book.info.obtain_method = "; ".join(method_parts)

        logger.info("解析到 %s 卷: %s", len(book.volumes), [volume.title for volume in book.volumes])

    def _get_paragraph_text(self, p_element) -> str:
        result_parts = []
        for content in p_element.children:
            if getattr(content, "name", None) == "br":
                continue
            if hasattr(content, "name"):
                text = content.get_text()
                if text:
                    result_parts.append(text.strip())
            else:
                text = str(content).strip()
                if text:
                    result_parts.append(text)
        return "\n".join(result_parts)

    def extract_book_links(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not href.startswith("/ys/") or href.startswith("/ys/文件:") or "action=" in href:
                continue
            title = link.get_text(strip=True) or link.get("title", "")
            if not title or title in ["首页", "书籍一览"]:
                continue
            if title in [
                "角色一览",
                "武器一览",
                "圣遗物一览",
                "成就一览",
                "食谱一览",
                "事件一览",
                "地图一览",
                "志异一览",
                "编年史一览",
                "创建新页面",
                "任务道具一览",
            ]:
                continue
            clean_href = href[4:] if href.startswith("/ys/") else href.lstrip("/")
            links.append({"title": title, "url": f"{self.base_url}{clean_href}"})

        seen = set()
        unique_links = []
        for link in links:
            if link["title"] not in seen:
                seen.add(link["title"])
                unique_links.append(link)
        return unique_links
