"""圣遗物页面 HTML 解析器"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ArtifactPiece:
    """圣遗物部件"""
    名称: str = ""
    类型: str = ""  # 生之花、死之羽、时之沙、空之杯、理之冠
    描述: str = ""
    故事: str = ""


@dataclass
class 获取途径项:
    """获取途径项（统一结构）"""
    类型: str = ""  # 副本、NPC、探索奖励、精英怪物、BOSS
    副本类型: str = ""
    副本名称: str = ""
    副本等级: str = ""
    星级: str = ""
    NPC姓名: str = ""
    获取方式: str = ""
    详细描述: str = ""


@dataclass
class ArtifactInfo:
    """圣遗物套装基本信息"""
    套装名称: str = ""
    稀有度: str = ""       # 如"4-5星"
    TAG: str = ""          # 伤害、后台触发、月曜
    实装版本: str = ""     # 月之四
    两件套效果: str = ""   # 元素精通提高80点（ dataclass 字段名用中文数字避免标识符冲突）
    四件套效果: str = ""   # 装备者处于队伍后台时...
    部件列表: list = field(default_factory=list)  # List of ArtifactPiece
    获取途径: list = field(default_factory=list)  # List[获取途径项]


@dataclass
class Artifact:
    """圣遗物完整数据"""
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
        """解析圣遗物详情页 HTML

        Args:
            html: 页面 HTML 内容
            title: 圣遗物标题
            url: 页面 URL

        Returns:
            Artifact 对象
        """
        soup = BeautifulSoup(html, "html.parser")
        artifact = Artifact(title=title, url=url)

        # 解析基本信息
        self._parse_artifact_info(soup, artifact)

        # 解析圣遗物故事
        self._parse_story(soup, artifact)

        return artifact

    def _parse_artifact_info(self, soup: BeautifulSoup, artifact: Artifact) -> None:
        """解析圣遗物基本信息

        HTML 结构示例（晨星与月的晓歌）：
        <div class="name">晨星与月的晓歌</div>
        <div class="star"><img alt="圣遗物套装-4星.png"...>~<img alt="圣遗物套装-5星.png"...></div>
        <div class="tag"><b>TAG：</b>伤害、后台触发、月曜</div>
        <div class="tag" style="margin:0"><b>实装版本：</b>月之四</div>
        <table class="effect"><tr><td>2件套</td><td>...</td></tr>...</table>
        """
        # 1. 解析套装名称
        name_div = soup.find("div", class_="name")
        if name_div:
            artifact.info.套装名称 = name_div.get_text(strip=True)

        # 2. 解析稀有度（从星级图片 alt 文本获取范围）
        star_div = soup.find("div", class_="star")
        if star_div:
            # 查找所有星级图片
            star_imgs = star_div.find_all("img", alt=re.compile(r"圣遗物套装-\d+星"))
            if len(star_imgs) >= 2:
                # 获取最小和最大星级
                stars = []
                for img in star_imgs:
                    alt = img.get("alt", "")
                    match = re.search(r"圣遗物套装-(\d+)星", alt)
                    if match:
                        stars.append(int(match.group(1)))
                if stars:
                    min_star = min(stars)
                    max_star = max(stars)
                    if min_star == max_star:
                        artifact.info.稀有度 = f"{min_star}星"
                    else:
                        artifact.info.稀有度 = f"{min_star}-{max_star}星"
            elif len(star_imgs) == 1:
                alt = star_imgs[0].get("alt", "")
                match = re.search(r"圣遗物套装-(\d+)星", alt)
                if match:
                    artifact.info.稀有度 = f"{match.group(1)}星"

        # 3. 解析 TAG 和实装版本
        tag_divs = soup.find_all("div", class_="tag")
        for tag_div in tag_divs:
            text = tag_div.get_text(strip=True)
            if text.startswith("TAG："):
                artifact.info.TAG = text.replace("TAG：", "").strip()
            elif text.startswith("实装版本："):
                artifact.info.实装版本 = text.replace("实装版本：", "").strip()

        # 4. 解析 2件套/4件套效果
        effect_table = soup.find("table", class_="effect")
        if effect_table:
            rows = effect_table.find_all("tr")
            for row in rows:
                tds = row.find_all("td")
                if len(tds) >= 2:
                    effect_type = tds[0].get_text(strip=True)
                    effect_content = tds[1].get_text(strip=True)
                    if effect_type == "2件套":
                        artifact.info.两件套效果 = effect_content
                    elif effect_type == "4件套":
                        artifact.info.四件套效果 = effect_content

        # 5. 解析圣遗物部件（5件套）
        self._parse_pieces(soup, artifact)

        # 6. 解析获取途径
        self._parse_get_method(soup, artifact)

    def _parse_pieces(self, soup: BeautifulSoup, artifact: Artifact) -> None:
        """解析圣遗物5件套

        HTML 结构：
        <div class="icon">
            <div class="autoimg"><img alt="晨星与月的晓歌生之花.png"...></div>
            <div class="main"><div class="up">献与月的华梦</div><div class="down">生之花</div></div>
        </div>
        """
        # 圣遗物部件类型
        piece_types = ["生之花", "死之羽", "时之沙", "空之杯", "理之冠"]

        # 优先从 resp-tabs-list 查找（这是 Tab 页签结构，更可靠）
        resp_tabs_list = soup.find("div", class_="resp-tabs-list")
        if resp_tabs_list:
            icon_divs = resp_tabs_list.find_all("div", class_="icon")
            for icon_div in icon_divs:
                up_div = icon_div.find("div", class_="up")
                down_div = icon_div.find("div", class_="down")

                if up_div and down_div:
                    piece_name = up_div.get_text(strip=True)
                    piece_type = down_div.get_text(strip=True)

                    if piece_type in piece_types:
                        piece = ArtifactPiece(
                            名称=piece_name,
                            类型=piece_type,
                            描述=""
                        )
                        artifact.info.部件列表.append(piece)

        # 如果 resp-tabs-list 没找到，尝试从左侧区域查找
        if len(artifact.info.部件列表) < 5:
            artifact.info.部件列表 = []  # 清空
            left_section = soup.find("div", class_=["col-md-6", "left"])
            if left_section:
                icon_divs = left_section.find_all("div", class_="icon")
                for icon_div in icon_divs:
                    up_div = icon_div.find("div", class_="up")
                    down_div = icon_div.find("div", class_="down")

                    if up_div and down_div:
                        piece_name = up_div.get_text(strip=True)
                        piece_type = down_div.get_text(strip=True)

                        if piece_type in piece_types:
                            piece = ArtifactPiece(
                                名称=piece_name,
                                类型=piece_type,
                                描述=""
                            )
                            artifact.info.部件列表.append(piece)

    def _parse_get_method(self, soup: BeautifulSoup, artifact: Artifact) -> None:
        """解析获取途径

        HTML 结构：
        <div class="get">
            <div class="title">获取方式</div>
            <div class="item">
                <div class="access">
                    <div class="head">...</div>
                    <div class="mid"></div>
                    <div class="title">副本</div>
                    <div class="content">（4星）：祝圣秘境：月童的库藏 Ⅰ至Ⅳ概率掉落。</div>
                </div>
                ...
            </div>
        </div>

        获取途径整理格式：
        - 副本（如：`（5星）：祝圣秘境：月童的库藏 Ⅲ至Ⅳ概率掉落。`将按以下格式保存）
          - 副本类型：祝圣秘境
          - 副本名称：月童的库藏
          - 副本等级：Ⅲ、Ⅳ
        - NPC
          - NPC姓名
          - 获取方式
        - 探索奖励
        - 精英怪物
        - BOSS
        """
        get_div = soup.find("div", class_="get")
        if not get_div:
            return

        access_divs = get_div.find_all("div", class_="access")
        for access in access_divs:
            title_div = access.find("div", class_="title")
            content_div = access.find("div", class_="content")

            if title_div and content_div:
                method_type = title_div.get_text(strip=True)
                method_content = content_div.get_text(strip=True)

                item = 获取途径项(类型=method_type)

                if method_type == "副本":
                    # 解析格式：（4星）：祝圣秘境：月童的库藏 Ⅰ至Ⅳ概率掉落。
                    # 或：（5星）：祝圣秘境：月童的库藏 Ⅲ至Ⅳ概率掉落。
                    self._parse_dungeon_content(item, method_content)
                elif method_type == "NPC":
                    # 解析格式：NPC姓名：获取方式
                    self._parse_npc_content(item, method_content)
                else:
                    # 探索奖励、精英怪物、BOSS 等直接存储详细描述
                    item.详细描述 = method_content

                artifact.info.获取途径.append(item)

    def _parse_dungeon_content(self, item: 获取途径项, content: str) -> None:
        """解析副本内容

        格式1（有星级）：（4星）：祝圣秘境：月童的库藏 Ⅰ至Ⅳ概率掉落。
        格式2（无星级）：华池岩岫：祝圣秘境：岩牢Ⅰ至Ⅲ概率掉落
        """
        # 匹配星级：（4星）：或（5星）：包括后面的冒号
        star_match = re.search(r"^（(\d+)星）：", content)
        if star_match:
            item.星级 = f"{star_match.group(1)}星"
            content = content[star_match.end():].strip()

        # 判断是否有祝圣秘境作为中间标签
        # 格式1：有祝圣秘境在前面，后面跟着副本名称（如：祝圣秘境：月童的库藏）
        # 格式2：有祝圣秘境在中间，前后是副本名称的组成部分（如：华池岩岫：祝圣秘境：岩牢）
        if "：祝圣秘境：" in content:
            # 格式2：华池岩岫：祝圣秘境：岩牢Ⅰ至Ⅲ概率掉落
            # 副本类型固定为"祝圣秘境"
            # 副本名称 = "华池岩岫：岩牢"（前部分 + ： + 后部分）
            parts = content.split("：祝圣秘境：", 1)
            if len(parts) >= 2:
                item.副本类型 = "祝圣秘境"
                remaining = parts[0].strip() + "：" + parts[1].strip()
            else:
                remaining = content
        else:
            # 格式1：祝圣秘境：月童的库藏 Ⅰ至Ⅳ概率掉落。或直接是副本名称
            parts = content.split("：", 1)
            if len(parts) >= 2:
                item.副本类型 = parts[0].strip()
                remaining = parts[1].strip()
            else:
                remaining = content

        # 解析副本名称和等级
        # 格式：月童的库藏 Ⅰ至Ⅳ概率掉落。或  岩牢Ⅰ至Ⅲ
        # 使用正则匹配等级（罗马数字+至+罗马数字 或 单独罗马数字）
        level_match = re.search(r"([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+至[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)", remaining)
        if level_match:
            level_text = level_match.group(1)
            if "至" in level_text:
                # Ⅰ至Ⅳ 转换为 Ⅰ~Ⅳ
                level_parts = level_text.split("至")
                item.副本等级 = f"{level_parts[0]}~{level_parts[1]}"
            else:
                item.副本等级 = level_text
            # 副本名称是等级前面的部分
            name_part = remaining[:level_match.start()].strip()
            item.副本名称 = name_part
            # 详细描述是等级后面的部分
            item.详细描述 = remaining[level_match.end():].strip()
        else:
            item.副本名称 = remaining

    def _parse_npc_content(self, item: 获取途径项, content: str) -> None:
        """解析NPC内容

        格式：NPC姓名：获取方式
        """
        parts = content.split("：", 1)
        if len(parts) >= 2:
            item.NPC姓名 = parts[0].strip()
            item.获取方式 = parts[1].strip()
        else:
            item.NPC姓名 = content

    def _parse_story(self, soup: BeautifulSoup, artifact: Artifact) -> None:
        """解析圣遗物故事（lore）

        HTML 结构：
        <div class="relic">
            <div class="resp-tabs-container">
                <div class="resp-tab-content" style="display: none;">
                    <div class="story">曾经有一个时代...<br/>
                    <p>那时，高天所降下的律法...</p>
                    </div><br/><br/>
                    <div class="item">古时为空月女神塑像的工匠...</div>
                </div>
                ...
            </div>
        </div>

        每个 <br/> 都是一个换行符：
        - 不连续单个 <br/> 使用一个换行符 \n 代替
        - 连续的两个如 <br/><br/> 使用两个如 \n\n 代替
        """
        # 查找圣遗物故事容器
        relic_div = soup.find("div", class_="relic")
        if not relic_div:
            return

        # 查找 resp-tabs-container
        tabs_container = relic_div.find("div", class_="resp-tabs-container")
        if not tabs_container:
            return

        # 收集所有 piece 的 lore，分布到各部件的"故事"字段
        tab_contents = tabs_container.find_all("div", class_="resp-tab-content")

        for i, tab_content in enumerate(tab_contents):
            # 获取该 tab 对应的部件
            if i >= len(artifact.info.部件列表):
                continue

            piece = artifact.info.部件列表[i]

            # 解析故事文本
            story_div = tab_content.find("div", class_="story")
            if story_div:
                story_text = self._clean_story_text(story_div)
                piece.故事 = story_text

            # 解析道具描述
            item_div = tab_content.find("div", class_="item")
            if item_div:
                item_text = item_div.get_text(strip=True)
                if item_text:
                    piece.描述 = item_text

    def _clean_story_text(self, story_div) -> str:
        """清理故事文本，处理换行

        Args:
            story_div: BeautifulSoup 的故事 div 元素

        Returns:
            清理后的文本
        """
        # 获取内部内容
        html_content = story_div.decode_contents()

        # 重要：原始 HTML 中 <br/> 后面可能有换行符，需要先去除
        html_content = html_content.replace('\n', '')

        # 处理连续 br 的替换
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
            lines = [line.strip() for line in p.split('\n') if line.strip()]
            if lines:
                cleaned_paragraphs.append('\n'.join(lines))

        return "\n\n".join(cleaned_paragraphs)

    def extract_artifact_links(self, html: str) -> list[dict]:
        """从圣遗物图鉴页面提取所有圣遗物链接

        注意：由于没有圣遗物图鉴列表页面的 HTML 样本，
        该方法的实现暂时基于武器图鉴的 visible-xs 模式。
        实际使用时需要根据实际页面结构调整。

        Args:
            html: 圣遗物图鉴页面 HTML

        Returns:
            圣遗物链接列表，每项包含 title 和 url
        """
        soup = BeautifulSoup(html, "html.parser")
        links = []

        # 尝试使用与武器相同的模式：visible-xs
        visible_xs_divs = soup.find_all("div", class_="visible-xs")

        for vis_div in visible_xs_divs:
            for a in vis_div.find_all("a", href=True):
                href = a["href"]
                if not href.startswith("/ys/"):
                    continue
                if href.startswith("/ys/文件:") or "action=" in href:
                    continue

                title = a.get_text(strip=True)
                if not title:
                    continue

                # 构建 URL
                if href.startswith("/ys/"):
                    clean_href = href[4:]
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
