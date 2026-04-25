"""武器页面 HTML 解析器"""

import logging
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ArmInfo:
    名称: str = ""
    稀有度: str = ""
    性能描述文本: str = ""
    武器技能: str = ""
    武器技能文本描述: str = ""
    武器介绍: str = ""
    实装版本: str = ""
    获取途径: str = ""
    武器类型: str = ""
    武器TAG: str = ""
    突破材料: list = field(default_factory=list)
    故事: str = ""


@dataclass
class Arm:
    title: str
    url: str = ""
    fetched_at: str = ""
    info: ArmInfo = field(default_factory=ArmInfo)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "fetched_at": self.fetched_at,
            "info": {
                "名称": self.info.名称,
                "稀有度": self.info.稀有度,
                "性能描述文本": self.info.性能描述文本,
                "武器技能": self.info.武器技能,
                "武器技能文本描述": self.info.武器技能文本描述,
                "武器介绍": self.info.武器介绍,
                "实装版本": self.info.实装版本,
                "获取途径": self.info.获取途径,
                "武器类型": self.info.武器类型,
                "武器TAG": self.info.武器TAG,
                "突破材料": self.info.突破材料,
                "故事": self.info.故事,
            },
        }


class ArmsParser:
    """武器页面 HTML 解析器"""

    def __init__(self, base_url: str = "https://wiki.biligame.com/ys/"):
        self.base_url = base_url

    def parse_arm_page(self, html: str, title: str, url: str = "") -> Arm:
        soup = BeautifulSoup(html, "html.parser")
        arm = Arm(title=title, url=url)
        self._parse_arm_info(soup, arm)
        self._parse_story(soup, arm)
        return arm

    def _parse_arm_info(self, soup: BeautifulSoup, arm: Arm) -> None:
        headline = soup.find("span", class_="mw-headline")
        if headline:
            arm.info.名称 = headline.get_text(strip=True)

        rarity_div = soup.find("div", style=re.compile(r"color:#FFAF52"))
        if rarity_div:
            arm.info.稀有度 = f"{rarity_div.get_text(strip=True).count('★')}星"

        for paragraph in soup.find_all("p"):
            text = paragraph.get_text(strip=True)
            if "攻击" in text or "防御" in text or "生命" in text:
                clean_text = self._clean_stats_text(paragraph)
                if clean_text:
                    arm.info.性能描述文本 = clean_text
                    break

        skill_div = soup.find("div", class_="card-title2", style=re.compile(r"margin-top:16px"))
        if skill_div:
            skill_text = skill_div.get_text(strip=True)
            if "武器技能 - " in skill_text:
                arm.info.武器技能 = skill_text.split("武器技能 - ", 1)[1]
            elif skill_text.startswith("武器技能"):
                arm.info.武器技能 = skill_text.replace("武器技能", "").strip()

        if arm.info.武器技能:
            skill_name_div = soup.find("div", class_="card-title2", style=re.compile(r"margin-top:16px"))
            if skill_name_div:
                next_sibling = skill_name_div.find_next_sibling("div", style=re.compile(r"margin-top:8px"))
                if next_sibling:
                    arm.info.武器技能文本描述 = next_sibling.get_text(strip=True)

        arm.info.突破材料 = self._parse_ascension_materials(soup)
        self._parse_card_fields(soup, arm)

    def _clean_stats_text(self, p_element) -> str:
        parts = []
        for content in p_element.children:
            if getattr(content, "name", None) == "br":
                continue
            if hasattr(content, "name"):
                text = content.get_text()
                if text:
                    parts.append(text.strip())
            else:
                text = str(content)
                if text.strip():
                    parts.append(text.strip())
        return "".join(parts).replace("///", "/").replace("//", "/")

    def _parse_ascension_materials(self, soup: BeautifulSoup) -> list:
        mat_rows = soup.find_all("td", class_="YS-MatRow")
        if not mat_rows:
            return []

        materials_by_position: dict[int, list[str]] = {}
        for row in mat_rows:
            for position, mat_div in enumerate(row.find_all("div", class_="YSCard-BtnMatInfo")):
                materials_by_position.setdefault(position, [])
                img = mat_div.find("img")
                if img and img.get("alt"):
                    material_name = img["alt"].replace(".png", "")
                    if material_name and material_name not in materials_by_position[position]:
                        materials_by_position[position].append(material_name)

        materials = []
        for position in range(max(materials_by_position.keys()) + 1):
            materials.extend(materials_by_position.get(position, []))
        return materials

    def _parse_card_fields(self, soup: BeautifulSoup, arm: Arm) -> None:
        for container in soup.find_all("div", style=re.compile(r"margin:16px 0 0 0")):
            title_div = container.find("div", class_="card-title3")
            content_div = container.find("div", class_="card-content3")
            if not title_div or not content_div:
                continue
            title = title_div.get_text(strip=True)
            content = content_div.get_text(strip=True)
            if not content:
                continue
            if title == "武器介绍":
                arm.info.武器介绍 = content
            elif title == "获取途径":
                arm.info.获取途径 = content
            elif title == "实装版本":
                arm.info.实装版本 = content
            elif title == "武器类型":
                arm.info.武器类型 = content
            elif title == "武器TAG":
                arm.info.武器TAG = content

    def _parse_story(self, soup: BeautifulSoup, arm: Arm) -> None:
        story_div = soup.find("div", id="mc_collapse-1")
        if not story_div:
            return
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
        arm.info.故事 = "\n\n".join(paragraphs)

    def extract_arm_links(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for vis_div in soup.find_all("div", class_="visible-xs"):
            for link in vis_div.find_all("a", href=True):
                href = link["href"]
                if not href.startswith("/ys/") or href.startswith("/ys/文件:") or "action=" in href:
                    continue
                title = link.get_text(strip=True)
                if not title or title in ["首页", "武器图鉴"]:
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
