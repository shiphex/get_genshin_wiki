"""圣遗物页面 HTML 解析器"""

import logging
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ArtifactPiece:
    名称: str = ""
    类型: str = ""
    描述: str = ""
    故事: str = ""


@dataclass
class 获取途径项:
    类型: str = ""
    副本类型: str = ""
    副本名称: str = ""
    副本等级: str = ""
    星级: str = ""
    NPC姓名: str = ""
    获取方式: str = ""
    详细描述: str = ""


@dataclass
class ArtifactInfo:
    套装名称: str = ""
    稀有度: str = ""
    TAG: str = ""
    实装版本: str = ""
    两件套效果: str = ""
    四件套效果: str = ""
    部件列表: list = field(default_factory=list)
    获取途径: list = field(default_factory=list)


@dataclass
class Artifact:
    title: str
    url: str = ""
    fetched_at: str = ""
    info: ArtifactInfo = field(default_factory=ArtifactInfo)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "fetched_at": self.fetched_at,
            "info": {
                "套装名称": self.info.套装名称,
                "稀有度": self.info.稀有度,
                "TAG": self.info.TAG,
                "实装版本": self.info.实装版本,
                "2件套效果": self.info.两件套效果,
                "4件套效果": self.info.四件套效果,
                "部件列表": [
                    {
                        "名称": piece.名称,
                        "类型": piece.类型,
                        "描述": piece.描述,
                        "故事": piece.故事,
                    }
                    for piece in self.info.部件列表
                ],
                "获取途径": [
                    {
                        "类型": item.类型,
                        "副本类型": item.副本类型,
                        "副本名称": item.副本名称,
                        "副本等级": item.副本等级,
                        "星级": item.星级,
                        "NPC姓名": item.NPC姓名,
                        "获取方式": item.获取方式,
                        "详细描述": item.详细描述,
                    }
                    for item in self.info.获取途径
                ],
            },
        }


class ArtifactsParser:
    """圣遗物页面 HTML 解析器"""

    def __init__(self, base_url: str = "https://wiki.biligame.com/ys/"):
        self.base_url = base_url

    def parse_artifact_page(self, html: str, title: str, url: str = "") -> Artifact:
        soup = BeautifulSoup(html, "html.parser")
        artifact = Artifact(title=title, url=url)
        self._parse_artifact_info(soup, artifact)
        self._parse_story(soup, artifact)
        return artifact

    def _parse_artifact_info(self, soup: BeautifulSoup, artifact: Artifact) -> None:
        name_div = soup.find("div", class_="name")
        if name_div:
            artifact.info.套装名称 = name_div.get_text(strip=True)

        star_div = soup.find("div", class_="star")
        if star_div:
            stars = []
            for img in star_div.find_all("img", alt=re.compile(r"圣遗物套装-\d+星")):
                match = re.search(r"圣遗物套装-(\d+)星", img.get("alt", ""))
                if match:
                    stars.append(int(match.group(1)))
            if stars:
                artifact.info.稀有度 = f"{min(stars)}-{max(stars)}星" if min(stars) != max(stars) else f"{stars[0]}星"

        for tag_div in soup.find_all("div", class_="tag"):
            text = tag_div.get_text(strip=True)
            if text.startswith("TAG："):
                artifact.info.TAG = text.replace("TAG：", "").strip()
            elif text.startswith("实装版本："):
                artifact.info.实装版本 = text.replace("实装版本：", "").strip()

        effect_table = soup.find("table", class_="effect")
        if effect_table:
            for row in effect_table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                effect_type = cells[0].get_text(strip=True)
                effect_content = cells[1].get_text(strip=True)
                if effect_type == "2件套":
                    artifact.info.两件套效果 = effect_content
                elif effect_type == "4件套":
                    artifact.info.四件套效果 = effect_content

        self._parse_pieces(soup, artifact)
        self._parse_get_method(soup, artifact)

    def _parse_pieces(self, soup: BeautifulSoup, artifact: Artifact) -> None:
        piece_types = ["生之花", "死之羽", "时之沙", "空之杯", "理之冠"]

        def extract_icon_info(icon_div):
            # Handle both direct up/down and nested main/up/down structure
            up_div = icon_div.find("div", class_="up") or icon_div.find("div", class_="main")
            down_div = icon_div.find("div", class_="down")
            if up_div:
                # If up is the main div, look for nested up/down
                if up_div.get("class") == ["main"]:
                    up_text = up_div.find("div", class_="up").get_text(strip=True) if up_div.find("div", class_="up") else ""
                    down_text = up_div.find("div", class_="down").get_text(strip=True) if up_div.find("div", class_="down") else ""
                else:
                    up_text = up_div.get_text(strip=True)
                    down_text = down_div.get_text(strip=True) if down_div else ""
            else:
                up_text = ""
                down_text = ""
            return up_text, down_text

        resp_tabs_list = soup.find("div", class_="resp-tabs-list")
        if resp_tabs_list:
            for icon_div in resp_tabs_list.find_all("div", class_="icon"):
                up_text, down_text = extract_icon_info(icon_div)
                if up_text and down_text and down_text in piece_types:
                    artifact.info.部件列表.append(
                        ArtifactPiece(
                            名称=up_text,
                            类型=down_text,
                        )
                    )

        if len(artifact.info.部件列表) == 0:
            left_section = soup.find("div", class_=["col-md-6", "left"])
            if left_section:
                for icon_div in left_section.find_all("div", class_="icon"):
                    up_text, down_text = extract_icon_info(icon_div)
                    if up_text and down_text and down_text in piece_types:
                        artifact.info.部件列表.append(
                            ArtifactPiece(
                                名称=up_text,
                                类型=down_text,
                            )
                        )

    def _parse_get_method(self, soup: BeautifulSoup, artifact: Artifact) -> None:
        get_div = soup.find("div", class_="get")
        if not get_div:
            return

        for access in get_div.find_all("div", class_="access"):
            title_div = access.find("div", class_="title")
            content_div = access.find("div", class_="content")
            if not title_div or not content_div:
                continue

            item = 获取途径项(类型=title_div.get_text(strip=True))
            method_content = content_div.get_text(strip=True)
            if item.类型 == "副本":
                self._parse_dungeon_content(item, method_content)
            elif item.类型 == "NPC":
                self._parse_npc_content(item, method_content)
            else:
                item.详细描述 = method_content
            artifact.info.获取途径.append(item)

    def _parse_dungeon_content(self, item: 获取途径项, content: str) -> None:
        star_match = re.search(r"^（(\d+)星）：", content)
        if star_match:
            item.星级 = f"{star_match.group(1)}星"
            content = content[star_match.end():].strip()

        if "：祝圣秘境：" in content:
            before, after = content.split("：祝圣秘境：", 1)
            item.副本类型 = "祝圣秘境"
            remaining = f"{before.strip()}：{after.strip()}"
        else:
            parts = content.split("：", 1)
            if len(parts) >= 2:
                item.副本类型 = parts[0].strip()
                remaining = parts[1].strip()
            else:
                remaining = content

        level_match = re.search(r"([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+至[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)", remaining)
        if level_match:
            level_text = level_match.group(1)
            if "至" in level_text:
                start, end = level_text.split("至", 1)
                item.副本等级 = f"{start}~{end}"
            else:
                item.副本等级 = level_text
            item.副本名称 = remaining[:level_match.start()].strip()
            item.详细描述 = remaining[level_match.end():].strip()
        else:
            item.副本名称 = remaining

    def _parse_npc_content(self, item: 获取途径项, content: str) -> None:
        parts = content.split("：", 1)
        if len(parts) >= 2:
            item.NPC姓名 = parts[0].strip()
            item.获取方式 = parts[1].strip()
        else:
            item.NPC姓名 = content

    def _parse_story(self, soup: BeautifulSoup, artifact: Artifact) -> None:
        relic_div = soup.find("div", class_="relic")
        if not relic_div:
            return

        tabs_container = relic_div.find("div", class_="resp-tabs-container")
        if not tabs_container:
            return

        for index, tab_content in enumerate(tabs_container.find_all("div", class_="resp-tab-content")):
            if index >= len(artifact.info.部件列表):
                continue
            piece = artifact.info.部件列表[index]
            story_div = tab_content.find("div", class_="story")
            if story_div:
                piece.故事 = self._clean_story_text(story_div)
            item_div = tab_content.find("div", class_="item")
            if item_div:
                piece.描述 = item_div.get_text(strip=True)

    def _clean_story_text(self, story_div) -> str:
        html_content = story_div.decode_contents().replace("\n", "")

        def replace_consecutive_brs(match):
            return "\n" * len(re.findall(r"<br\s*/?>", match.group(0)))

        html_content = re.sub(r"(<br\s*/?>)+", replace_consecutive_brs, html_content)
        html_content = re.sub(r"</?p[^>]*>", "", html_content)
        html_content = re.sub(r"<[^>]+>", "", html_content)

        paragraphs = []
        for paragraph in html_content.split("\n\n"):
            lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
            if lines:
                paragraphs.append("\n".join(lines))
        return "\n\n".join(paragraphs)

    def extract_artifact_links(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for vis_div in soup.find_all("div", class_="visible-xs"):
            for link in vis_div.find_all("a", href=True):
                href = link["href"]
                if not href.startswith("/ys/") or href.startswith("/ys/文件:") or "action=" in href:
                    continue
                title = link.get_text(strip=True)
                if not title or title in ["首页", "圣遗物图鉴"]:
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
