"""书籍页面 HTML 解析器"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class BookVolume:
    """书籍卷信息"""
    title: str  # 卷标题，如"第一卷"、"终北祷歌集·其一"
    content: str = ""  # 卷文本内容
    obtain_method: Optional[str] = None  # 获取方式


@dataclass
class BookInfo:
    """书籍基本信息"""
    name: str = ""
    volumes_count: int = 0
    rarity: str = ""
    genre: str = ""  # 体裁
    country: str = ""  # 国家
    version: str = ""  # 实装版本
    gallery: str = ""  # 图鉴
    related_characters: list = field(default_factory=list)  # 相关角色
    obtain_method: str = ""  # 获取方式（总览）
    _obtain_methods: dict = field(default_factory=dict)  # 每卷获取方式映射


@dataclass
class Book:
    """书籍完整数据"""
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
                    "title": v.title,
                    "content": v.content,
                    "obtain_method": v.obtain_method,
                }
                for v in self.volumes
            ],
        }


class BookParser:
    """书籍页面 HTML 解析器"""

    def __init__(self, base_url: str = "https://wiki.biligame.com/ys/"):
        self.base_url = base_url

    def parse_book_page(self, html: str, title: str, url: str = "") -> Book:
        """解析书籍详情页 HTML

        Args:
            html: 页面 HTML 内容
            title: 书籍标题
            url: 页面 URL

        Returns:
            Book 对象
        """
        soup = BeautifulSoup(html, "html.parser")
        book = Book(title=title, url=url)

        # 解析基本信息（从 Infobox）
        self._parse_infobox(soup, book)

        # 解析卷内容
        self._parse_volumes(soup, book)

        return book

    def _parse_infobox(self, soup: BeautifulSoup, book: Book) -> None:
        """解析 Infobox 中的书籍信息

        HTML 结构（终北祷歌集）：
        <table class="wikitable boxright">
            <tr><th colspan="2">终北祷歌集</th></tr>
            <tr><th>卷数</th><td>共3卷</td></tr>
            <tr><th>稀有度</th><td><img alt="4星.png"/> </td></tr>
            <tr><th>体裁</th><td>诗歌</td></tr>
            <tr><th>国家</th><td>挪德卡莱</td></tr>
            <tr><th>实装版本</th><td>月之一</td></tr>
            <tr><th>图鉴</th><td>是</td></tr>
            <tr><th>相关角色</th><td><a href="/ys/安洛丝">安洛丝</a></td></tr>
            <tr><th colspan="2">获取方式</th></tr>
            <tr><th colspan="2">终北祷歌•上</th></tr>
            <tr><td colspan="2">霜月之坊聚所共建到满级后可拾取</td></tr>
            ...
        """
        # 查找 infobox 表格（class="wikitable boxright"）
        infobox_table = soup.find("table", class_="wikitable")
        if not infobox_table:
            logger.warning(f"未找到 Infobox: {book.title}")
            return

        # 用于存储每卷获取方式的映射
        obtain_methods = {}
        current_volume_title = None

        rows = infobox_table.find_all("tr")
        for row in rows:
            header = row.find("th")
            data = row.find("td")

            # 检查是否是跨列标题（包含卷名或获取方式标记）
            if header and header.get("colspan") == "2":
                header_text = header.get_text(strip=True)
                if "获取方式" in header_text:
                    # 跳过"获取方式"标题本身
                    continue
                elif header_text:
                    # 这可能是卷名
                    current_volume_title = header_text
                    if current_volume_title not in obtain_methods:
                        obtain_methods[current_volume_title] = None

            # 如果有 data 单元格
            if data and current_volume_title:
                data_text = data.get_text(strip=True)
                if data_text and "获取方式" not in data_text:
                    obtain_methods[current_volume_title] = data_text
                    current_volume_title = None  # 重置

            # 处理常规的 key-value 行
            if header and data and header.get("colspan") != "2":
                key = header.get_text(strip=True)
                value = data.get_text(strip=True)

                # 映射字段
                if key in ["名称", "名称/外文名称"]:
                    book.info.name = value
                elif key == "卷数":
                    book.info.volumes_count = value
                elif key == "稀有度":
                    # 稀有度可能是图片，提取 alt 文本
                    img = data.find("img")
                    if img and img.get("alt"):
                        book.info.rarity = img.get("alt").replace(".png", "")
                    else:
                        book.info.rarity = value
                elif key in ["体裁", "类型"]:
                    book.info.genre = value
                elif key == "国家":
                    book.info.country = value
                elif key in ["実装版本", "实装版本"]:
                    book.info.version = value
                elif key in ["图鉴", "画廊"]:
                    book.info.gallery = value
                elif key in ["相关角色", "角色"]:
                    links = data.find_all("a")
                    characters = []
                    for a in links:
                        if a.get("href", "").startswith("/ys/"):
                            text = a.get_text(strip=True)
                            if text:  # 跳过只有图片的链接
                                characters.append(text)
                    # 去重
                    book.info.related_characters = list(dict.fromkeys(characters))

        # 将获取方式映射存储到 book.info 中
        book.info._obtain_methods = obtain_methods

        # 如果名称为空，使用页面标题
        if not book.info.name:
            book.info.name = book.title

    def _parse_volumes(self, soup: BeautifulSoup, book: Book) -> None:
        """解析每卷内容

        HTML 结构：
        <h2><span class="mw-headline" id="卷名">卷名</span></h2>
        <p>第一段内容<br />换行内容</p>
        <p>第二段内容</p>
        ...
        <h2><span class="mw-headline" id="卷名2">卷名2</span></h2>
        ...
        """
        # 获取从 infobox 中解析的获取方式映射
        obtain_methods = getattr(book.info, "_obtain_methods", {})

        # 查找所有章节标题（通常在 h2 中）
        headlines = soup.find_all("span", class_="mw-headline")

        for i, headline in enumerate(headlines):
            # 获取卷标题
            volume_title = headline.get_text(strip=True)
            if not volume_title:
                continue

            # 跳过目录、导航等非卷内容
            skip_keywords = ["目录", "导航", "参见", "注释", "参考资料", "外部链接"]
            if any(kw in volume_title for kw in skip_keywords):
                continue

            # 收集该卷内容
            content_parts = []

            # 从 infobox 获取该卷的获取方式
            obtain_method = obtain_methods.get(volume_title)

            # 找到下一个 headline 之间的所有元素
            current = headline.find_parent("h2")
            if not current:
                continue

            for sibling in current.find_next_siblings():
                # 遇到下一个 h2 停止
                if sibling.name == "h2":
                    break

                # 收集段落文本，保留 <br /> 换行格式
                if sibling.name == "p":
                    # 获取段落文本，保留 <br /> 标签的换行效果
                    text = self._get_paragraph_text(sibling)
                    if text:
                        content_parts.append(text)

            # 组装卷内容
            volume = BookVolume(
                title=volume_title,
                content="\n".join(content_parts),
                obtain_method=obtain_method,
            )
            book.volumes.append(volume)

        # 汇总所有卷的获取方式到 info.obtain_method
        if book.volumes:
            method_parts = []
            for vol in book.volumes:
                if vol.obtain_method:
                    method_parts.append(f"{vol.title}: {vol.obtain_method}")
            if method_parts:
                book.info.obtain_method = "; ".join(method_parts)

        logger.info(f"解析到 {len(book.volumes)} 卷: {[v.title for v in book.volumes]}")

    def _get_paragraph_text(self, p_element) -> str:
        """获取段落文本，保留 <br /> 标签的换行格式

        Args:
            p_element: BeautifulSoup 的 <p> 元素

        Returns:
            保留换行的文本
        """
        # 方法：先处理 <br /> 标签，将相邻的文本分开
        result_parts = []
        for content in p_element.children:
            if hasattr(content, 'name') and content.name == 'br':
                # <br /> 标签前后的文本用换行分隔
                continue
            elif hasattr(content, 'name'):
                # 其他标签（如 <b>, <a> 等）直接获取文本
                text = content.get_text()
                if text:
                    result_parts.append(text)
            else:
                # NavigableString，直接获取文本
                text = str(content)
                if text.strip():
                    result_parts.append(text.strip())

        # 将所有部分用换行连接
        return "\n".join(result_parts)

    def extract_book_links(self, html: str) -> list[dict]:
        """从书籍一览页面提取所有书籍链接

        Args:
            html: 书籍一览页面 HTML

        Returns:
            书籍链接列表，每项包含 title 和 url
        """
        soup = BeautifulSoup(html, "html.parser")
        links = []

        # 查找所有指向书籍页面的链接
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # 书籍详情页 URL 格式：/ys/书籍名
            # 过滤掉：文件页面、页面编辑链接、首页等
            if not href.startswith("/ys/"):
                continue
            if href.startswith("/ys/文件:") or "action=" in href:
                continue

            # 获取链接文本，优先使用文本内容，回退到 title 属性
            title = a.get_text(strip=True)
            if not title and a.get("title"):
                title = a["title"]
            if not title or title in ["首页", "书籍一览"]:
                continue

            # 过滤明显不是书籍的页面（只跳过明确的导航页面）
            skip_patterns = [
                "角色一览", "武器一览", "圣遗物一览", "成就一览", "食谱一览",
                "事件一览", "地图一览", "志异一览", "编年史一览"
            ]
            if title in skip_patterns:
                continue

            # 构建 URL（base_url 已经包含 /ys/，所以要去重）
            if href.startswith("/ys/"):
                clean_href = href[4:]  # 去掉 /ys/ 前缀
                full_url = f"{self.base_url}{clean_href}"
            else:
                full_url = f"{self.base_url}{href.lstrip('/')}"

            links.append({
                "title": title,
                "url": full_url,
            })

        # 去重
        seen = set()
        unique_links = []
        for link in links:
            if link["title"] not in seen:
                seen.add(link["title"])
                unique_links.append(link)

        return unique_links
