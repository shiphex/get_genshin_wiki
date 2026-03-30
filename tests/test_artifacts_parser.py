"""圣遗物解析器测试"""
import pytest

from src.parser.artifacts_parser import ArtifactsParser, Artifact, ArtifactInfo, ArtifactPiece, 获取途径项


class TestArtifactsParser:
    """ArtifactsParser 测试类"""

    def setup_method(self):
        """每个测试方法前 setup"""
        self.parser = ArtifactsParser(base_url="https://wiki.biligame.com/ys/")

    def test_artifact_to_dict(self):
        """测试 Artifact.to_dict() 方法"""
        artifact = Artifact(title="晨星与月的晓歌")
        artifact.info.套装名称 = "晨星与月的晓歌"
        artifact.info.稀有度 = "4-5星"
        artifact.info.TAG = "伤害、后台触发、月曜"
        artifact.info.实装版本 = "月之四"
        artifact.info.两件套效果 = "元素精通提高80点。"
        artifact.info.四件套效果 = "装备者处于队伍后台时，造成的月曜反应伤害提升20%；..."

        # 测试结构化获取途径
        dungeon1 = 获取途径项(
            类型="副本",
            副本类型="祝圣秘境",
            副本名称="月童的库藏",
            副本等级="Ⅰ、Ⅳ",
            星级="4星",
            详细描述="概率掉落"
        )
        artifact.info.获取途径.append(dungeon1)

        piece1 = ArtifactPiece(名称="献与月的华梦", 类型="生之花", 描述="生命值+4781")
        artifact.info.部件列表.append(piece1)

        result = artifact.to_dict()

        assert result["title"] == "晨星与月的晓歌"
        assert result["info"]["套装名称"] == "晨星与月的晓歌"
        assert result["info"]["稀有度"] == "4-5星"
        assert result["info"]["TAG"] == "伤害、后台触发、月曜"
        assert result["info"]["实装版本"] == "月之四"
        assert result["info"]["2件套效果"] == "元素精通提高80点。"
        assert result["info"]["4件套效果"] == "装备者处于队伍后台时，造成的月曜反应伤害提升20%；..."
        # 验证结构化获取途径
        assert len(result["info"]["获取途径"]) == 1
        assert result["info"]["获取途径"][0]["类型"] == "副本"
        assert result["info"]["获取途径"][0]["副本类型"] == "祝圣秘境"
        assert result["info"]["获取途径"][0]["副本名称"] == "月童的库藏"
        assert result["info"]["获取途径"][0]["副本等级"] == "Ⅰ、Ⅳ"
        assert result["info"]["获取途径"][0]["星级"] == "4星"
        assert len(result["info"]["部件列表"]) == 1
        assert result["info"]["部件列表"][0]["名称"] == "献与月的华梦"
        assert result["info"]["部件列表"][0]["类型"] == "生之花"
        assert result["info"]["部件列表"][0]["描述"] == "生命值+4781"

    def test_extract_artifact_links_basic(self):
        """测试从圣遗物图鉴页面提取链接（基于 visible-xs 模式）"""
        html = """
        <html>
        <body>
            <div class="visible-xs">
                <a href="/ys/如雷的盛怒">如雷的盛怒</a>
            </div>
            <div class="visible-xs">
                <a href="/ys/晨星与月的晓歌">晨星与月的晓歌</a>
            </div>
            <div class="visible-xs">
                <a href="/ys/如雷的盛怒">如雷的盛怒（重复）</a>
            </div>
            <a href="/ys/文件:test.png">test.png</a>
        </body>
        </html>
        """
        links = self.parser.extract_artifact_links(html)

        # 应该去重且过滤文件页面
        titles = [link["title"] for link in links]
        assert "如雷的盛怒" in titles
        assert "晨星与月的晓歌" in titles
        assert titles.count("如雷的盛怒") == 1  # 不重复
        assert "test.png" not in titles  # 过滤文件页面

    def test_skip_navigation_links(self):
        """测试跳过导航类链接"""
        html = """
        <html>
        <body>
            <a href="/ys/角色一览">角色一览</a>
            <a href="/ys/武器一览">武器一览</a>
            <a href="/ys/圣遗物一览">圣遗物一览</a>
            <div class="visible-xs">
                <a href="/ys/晨星与月的晓歌">晨星与月的晓歌</a>
            </div>
        </body>
        </html>
        """
        links = self.parser.extract_artifact_links(html)

        titles = [link["title"] for link in links]
        assert "角色一览" not in titles
        assert "武器一览" not in titles
        assert "圣遗物一览" not in titles
        assert "晨星与月的晓歌" in titles

    def test_clean_story_text(self):
        """测试故事文本清理（换行处理）"""
        html = """
        <html>
        <body>
            <div class="story">曾经有一个时代，牵引着原初天球的银轮，其数量依旧为三。<br/>
            <p>那时，高天所降下的律法尚未结集，人理的边界尚未划定。<br/>
            <br/><br/>
            神的子民散布在新造的园囿与山谷。</p>
            </div>
        </body>
        </html>
        """
        soup = __import__("bs4").BeautifulSoup(html, "html.parser")
        story_div = soup.find("div", class_="story")
        result = self.parser._clean_story_text(story_div)

        assert "曾经有一个时代" in result
        assert "牵引着原初天球的银轮" in result
        assert "\n" in result  # 应该有换行
