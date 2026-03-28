"""武器页面 HTML 解析器"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ArmInfo:
    """武器基本信息"""
    名称: str = ""
    稀有度: str = ""       # 如"5星"
    性能描述文本: str = ""  # 攻击力 46-608 /// 暴击率 7.2%-33.1%
    武器技能: str = ""     # 武器技能名称
    武器技能文本描述: str = ""  # 技能详细描述
    武器介绍: str = ""     # 武器介绍
    实装版本: str = ""     # 实装版本
    获取途径: str = ""      # 获取途径
    武器类型: str = ""     # 武器类型
    武器TAG: str = ""      # 武器TAG
    突破材料: list = field(default_factory=list)  # 突破材料列表
    故事: str = ""         # 故事文本


@dataclass
class Arm:
    """武器完整数据"""
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
        """解析武器详情页 HTML

        Args:
            html: 页面 HTML 内容
            title: 武器标题
            url: 页面 URL

        Returns:
            Arm 对象
        """
        soup = BeautifulSoup(html, "html.parser")
        arm = Arm(title=title, url=url)

        # 解析基本信息
        self._parse_arm_info(soup, arm)

        # 解析故事
        self._parse_story(soup, arm)

        return arm

    def _parse_arm_info(self, soup: BeautifulSoup, arm: Arm) -> None:
        """解析武器基本信息

        HTML 结构示例（狼的武功歌）：
        <span class="mw-headline" id="狼的武功歌"><b>狼的武功歌</b></span></h2>
        <div style="color:#FFAF52; font-size:x-large;">★★★★★</div>
        <p>攻击力 46-608 <span class="visible-xs-inline"><br /></span><span class="hidden-xs">///</span> 暴击率 7.2%-33.1%</p>
        <div class="card-title2" style="width:100%; margin-top:16px;">武器技能 - 不灭的骑士道</div>
        <div style="width:100%; margin-top:8px;">攻击速度提升10%...</div>
        """
        # 1. 解析名称（从 mw-headline 获取）
        headline = soup.find("span", class_="mw-headline")
        if headline:
            arm.info.名称 = headline.get_text(strip=True)

        # 2. 解析稀有度（数 ★ 字符）
        rarity_div = soup.find("div", style=re.compile(r"color:#FFAF52"))
        if rarity_div:
            stars = rarity_div.get_text(strip=True)
            star_count = stars.count("★")
            if star_count > 0:
                arm.info.稀有度 = f"{star_count}星"

        # 3. 解析性能描述文本（攻击力/暴击率等）
        # 查找包含"攻击力"或"防御力"等的 <p> 标签
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if "攻击" in text or "防御" in text or "生命" in text:
                # 清理文本，移除隐藏的额外内容
                clean_text = self._clean_stats_text(p)
                if clean_text:
                    arm.info.性能描述文本 = clean_text
                    break

        # 4. 解析武器技能
        skill_div = soup.find("div", class_="card-title2", style=re.compile(r"margin-top:16px"))
        if skill_div:
            skill_text = skill_div.get_text(strip=True)
            # 格式："武器技能 - 技能名"
            if "武器技能 - " in skill_text:
                arm.info.武器技能 = skill_text.split("武器技能 - ", 1)[1]
            elif skill_text.startswith("武器技能"):
                arm.info.武器技能 = skill_text.replace("武器技能", "").strip()

        # 5. 解析武器技能文本描述
        if arm.info.武器技能:
            # 技能描述在技能名称之后的 <div style="width:100%; margin-top:8px;">
            skill_name_div = soup.find("div", class_="card-title2", style=re.compile(r"margin-top:16px"))
            if skill_name_div:
                next_sibling = skill_name_div.find_next_sibling("div", style=re.compile(r"margin-top:8px"))
                if next_sibling:
                    arm.info.武器技能文本描述 = next_sibling.get_text(strip=True)

        # 6. 解析突破材料（按等级分组，同一位置的材料靠近放置）
        materials = self._parse_ascension_materials(soup)
        arm.info.突破材料 = materials

        # 7. 解析 card-title3/card-content3 字段（武器介绍、获取途径、实装版本、武器类型、武器TAG）
        self._parse_card_fields(soup, arm)

    def _clean_stats_text(self, p_element) -> str:
        """清理性能描述文本，移除额外的分隔符和空格

        Args:
            p_element: BeautifulSoup 的 <p> 元素

        Returns:
            清理后的文本
        """
        parts = []
        for content in p_element.children:
            if hasattr(content, 'name') and content.name == 'br':
                continue
            elif hasattr(content, 'name'):
                text = content.get_text()
                if text:
                    parts.append(text.strip())
            else:
                text = str(content)
                if text.strip():
                    parts.append(text.strip())

        result = "".join(parts)
        # 清理特殊分隔符
        result = result.replace("///", "/").replace("//", "/")
        return result

    def _parse_ascension_materials(self, soup: BeautifulSoup) -> list:
        """解析突破材料

        HTML 结构：
        <tr><th><big><b>20级</b></big><br />突破</th>
        <td class="YS-MatRow">
            <div class="YSCard-BtnMatInfo"><img alt="凛风奔狼的始龀.png"/>...</div>
            <div class="YSCard-BtnMatInfo"><img alt="深黯的裂眼.png"/>...</div>
            <div class="YSCard-BtnMatInfo"><img alt="新兵的徽记.png"/>...</div>
        </td></tr>

        Returns:
            突破材料列表，按等级分组（同一等级的材料按列靠近放置）
            每个位置只保留唯一的材料名称，并保持材料首次出现的顺序
        """
        # 查找所有突破材料行的 YS-MatRow
        mat_rows = soup.find_all("td", class_="YS-MatRow")

        if not mat_rows:
            return []

        # 收集每个位置的材料（保持首次出现的顺序，去重）
        # materials_by_pos[位置索引] = [材料名列表，保持顺序]
        materials_by_pos = {}

        for row in mat_rows:
            mat_divs = row.find_all("div", class_="YSCard-BtnMatInfo")
            for pos, mat_div in enumerate(mat_divs):
                if pos not in materials_by_pos:
                    materials_by_pos[pos] = []
                img = mat_div.find("img")
                if img and img.get("alt"):
                    mat_name = img["alt"].replace(".png", "")
                    if mat_name and mat_name not in materials_by_pos[pos]:
                        materials_by_pos[pos].append(mat_name)

        # 按位置顺序重组材料列表
        # 即：所有第1位材料放一起，所有第2位材料放一起...
        result = []
        max_pos = max(materials_by_pos.keys()) if materials_by_pos else -1
        for pos in range(max_pos + 1):
            if pos in materials_by_pos:
                result.extend(materials_by_pos[pos])

        return result

    def _parse_weapon_intro(self, soup: BeautifulSoup) -> str:
        """解析武器介绍

        武器介绍通常在性能描述之后，武器技能之前的 <p> 标签中
        """
        stats_p = None
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if "攻击" in text or "防御" in text or "生命" in text:
                stats_p = p
                break

        if not stats_p:
            return ""

        # 武器介绍在性能描述之后的 <p> 标签
        intro_parts = []
        for sibling in stats_p.find_next_siblings():
            if sibling.name == "div" and "card-title2" in sibling.get("class", []):
                break
            if sibling.name == "p":
                text = sibling.get_text(strip=True)
                if text and "武器技能" not in text:
                    intro_parts.append(text)

        return "\n".join(intro_parts) if intro_parts else ""

    def _parse_card_fields(self, soup: BeautifulSoup, arm: Arm) -> None:
        """解析 card-title3/card-content3 字段

        HTML 结构：
        <div style="margin:16px 0 0 0;">
        <div class="card-title3">武器介绍</div>
        <div class="card-content3">传说中，是继承了「北风」之名的瑞文伍德...</div>
        </div>

        字段包括：武器介绍、获取途径、实装版本、武器类型、武器TAG
        """
        # 查找所有包含 card-title3 的容器
        card_containers = soup.find_all("div", style=re.compile(r"margin:16px 0 0 0"))

        for container in card_containers:
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
        """解析故事文本

        HTML 结构：
        <div id="mc_collapse-1" class="panel-body panel-collapse collapse">
            在诗与酒的国度...。<br/>
            <p>在所有华美的诗篇...<br/>
            毕竟...<br/><br/>
            ...
        </div>

        每个 <br/> 都是一个换行符：
        - 不连续单个 <br/> 使用一个换行符 \n 代替
        - 连续的两个如 <br/><br/> 使用两个如 \n\n 代替
        - 依次类推
        """
        # 查找故事内容的 div
        story_div = soup.find("div", id="mc_collapse-1")
        if not story_div:
            return

        # 获取内部内容（不包含外层 div 标签）
        html_content = story_div.decode_contents()

        # 重要：原始 HTML 中 <br/> 后面可能有换行符，需要先去除
        # 这样可以准确计算连续的 br 数量
        html_content = html_content.replace('\n', '')

        import re
        # 处理连续 br 的替换：
        # n 个连续的 <br/> 替换为 n 个 \n
        def replace_consecutive_brs(match):
            count = len(re.findall(r'<br\s*/?>', match.group(0)))
            return '\n' * count

        # 匹配一个或多个连续的 <br/>
        html_content = re.sub(r'(<br\s*/?>)+', replace_consecutive_brs, html_content)

        # 移除 <p> 和 </p> 标签
        html_content = re.sub(r'</?p[^>]*>', '', html_content)

        # 移除所有剩余的 HTML 标签
        html_content = re.sub(r"<[^>]+>", "", html_content)

        # 清理：按 \n\n 分割成段落
        paragraphs = html_content.split('\n\n')

        # 清理每个段落
        cleaned_paragraphs = []
        for p in paragraphs:
            # 分割成行，清理每行
            lines = [line.strip() for line in p.split('\n') if line.strip()]
            if lines:
                # 同一段落内的行用换行符连接
                cleaned_paragraphs.append('\n'.join(lines))

        # 用双换行符连接段落
        arm.info.故事 = "\n\n".join(cleaned_paragraphs)

    def _get_paragraph_text(self, p_element) -> str:
        """获取段落文本，保留 <br /> 标签的换行格式

        Args:
            p_element: BeautifulSoup 的 <p> 元素

        Returns:
            保留换行的文本
        """
        result_parts = []
        for content in p_element.children:
            if hasattr(content, 'name') and content.name == 'br':
                continue
            elif hasattr(content, 'name'):
                text = content.get_text()
                if text:
                    result_parts.append(text)
            else:
                text = str(content)
                if text.strip():
                    result_parts.append(text.strip())

        return "\n".join(result_parts)

    def extract_arm_links(self, html: str) -> list[dict]:
        """从武器图鉴页面提取所有武器链接

        Args:
            html: 武器图鉴页面 HTML

        Returns:
            武器链接列表，每项包含 title 和 url
        """
        soup = BeautifulSoup(html, "html.parser")
        links = []

        # 武器都在 <div class="visible-xs"> 元素内
        visible_xs_divs = soup.find_all("div", class_="visible-xs")

        for vis_div in visible_xs_divs:
            # 查找该 div 内所有指向武器页面的链接
            for a in vis_div.find_all("a", href=True):
                href = a["href"]
                # 武器详情页 URL 格式：/ys/武器名
                if not href.startswith("/ys/"):
                    continue
                if href.startswith("/ys/文件:") or "action=" in href:
                    continue

                # 获取链接文本
                title = a.get_text(strip=True)
                if not title:
                    continue
                if not title or title in ["首页", "武器图鉴"]:
                    continue

                # 构建 URL
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
