"""武器解析器测试"""
import pytest

from src.parser.arms_parser import ArmsParser, Arm, ArmInfo


class TestArmsParser:
    """ArmsParser 测试类"""

    def setup_method(self):
        """每个测试方法前 setup"""
        self.parser = ArmsParser(base_url="https://wiki.biligame.com/ys/")

    def test_extract_arm_links_basic(self):
        """测试从武器图鉴页面提取链接"""
        html = """
        <html>
        <body>
            <div class="visible-xs">
                <a href="/ys/狼的武功歌">狼的武功歌</a>
            </div>
            <div class="visible-xs">
                <a href="/ys/风花节">风花节</a>
            </div>
            <div class="visible-xs">
                <a href="/ys/狼的武功歌">狼的武功歌（重复）</a>
            </div>
            <a href="/ys/文件:test.png">test.png</a>
        </body>
        </html>
        """
        links = self.parser.extract_arm_links(html)

        # 应该去重且过滤文件页面
        titles = [link["title"] for link in links]
        assert "狼的武功歌" in titles
        assert "风花节" in titles
        assert titles.count("狼的武功歌") == 1  # 不重复
        assert "test.png" not in titles  # 过滤文件页面

    def test_arm_to_dict(self):
        """测试 Arm.to_dict() 方法"""
        arm = Arm(title="测试武器")
        arm.info.名称 = "测试武器名"
        arm.info.稀有度 = "5星"
        arm.info.性能描述文本 = "攻击力 46-608"
        arm.info.武器技能 = "不灭的骑士道"
        arm.info.武器技能文本描述 = "攻击速度提升10%..."
        arm.info.突破材料 = ["材料1", "材料2"]

        result = arm.to_dict()

        assert result["title"] == "测试武器"
        assert result["info"]["名称"] == "测试武器名"
        assert result["info"]["稀有度"] == "5星"
        assert result["info"]["性能描述文本"] == "攻击力 46-608"
        assert result["info"]["武器技能"] == "不灭的骑士道"
        assert result["info"]["武器技能文本描述"] == "攻击速度提升10%..."
        assert result["info"]["突破材料"] == ["材料1", "材料2"]

    def test_skip_navigation_links(self):
        """测试跳过导航类链接"""
        html = """
        <html>
        <body>
            <a href="/ys/角色一览">角色一览</a>
            <a href="/ys/武器一览">武器一览</a>
            <a href="/ys/圣遗物一览">圣遗物一览</a>
            <div class="visible-xs">
                <a href="/ys/狼的武功歌">狼的武功歌</a>
            </div>
        </body>
        </html>
        """
        links = self.parser.extract_arm_links(html)

        titles = [link["title"] for link in links]
        assert "角色一览" not in titles
        assert "武器一览" not in titles
        assert "圣遗物一览" not in titles
        assert "狼的武功歌" in titles

    def test_clean_stats_text(self):
        """测试性能描述文本清理"""
        html = """
        <html>
        <body>
            <p>攻击力 46-608 <span class="visible-xs-inline"><br /></span><span class="hidden-xs">///</span> 暴击率 7.2%-33.1%</p>
        </body>
        </html>
        """
        soup = __import__("bs4").BeautifulSoup(html, "html.parser")
        p_element = soup.find("p")
        result = self.parser._clean_stats_text(p_element)

        assert "攻击力" in result
        assert "46-608" in result
        assert "暴击率" in result
        assert "7.2%-33.1%" in result
