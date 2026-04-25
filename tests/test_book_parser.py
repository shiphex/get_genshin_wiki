"""书籍解析器测试"""
import pytest

from src.parser.book_parser import BookParser, Book, BookVolume


class TestBookParser:
    """BookParser 测试类"""

    def setup_method(self):
        """每个测试方法前 setup"""
        self.parser = BookParser(base_url="https://wiki.biligame.com/ys/")

    def test_extract_book_links_basic(self):
        """测试从书籍一览页面提取链接"""
        html = """
        <html>
        <body>
            <a href="/ys/终北祷歌集">终北祷歌集</a>
            <a href="/ys/璃月港">璃月港</a>
            <a href="/ys/终北祷歌集">终北祷歌集（重复）</a>
            <a href="/ys/文件:test.png">test.png</a>
        </body>
        </html>
        """
        links = self.parser.extract_book_links(html)

        # 应该去重且过滤文件页面
        titles = [link["title"] for link in links]
        assert "终北祷歌集" in titles
        assert "璃月港" in titles
        assert titles.count("终北祷歌集") == 1  # 不重复
        assert "test.png" not in titles  # 过滤文件页面

    def test_parse_volumes_basic(self):
        """测试解析卷内容"""
        html = """
        <html>
        <body>
            <h2><span class="mw-headline" id="第一卷">第一卷</span></h2>
            <p>这是第一卷的第一段。</p>
            <p>这是第一卷的第二段。</p>
            <h2><span class="mw-headline" id="第二卷">第二卷</span></h2>
            <p>这是第二卷的内容。</p>
        </body>
        </html>
        """
        book = Book(title="测试书籍", url="https://wiki.biligame.com/ys/测试书籍")
        self.parser._parse_volumes(
            __import__("bs4").BeautifulSoup(html, "html.parser"),
            book
        )

        assert len(book.volumes) == 2
        assert book.volumes[0].title == "第一卷"
        assert "第一卷的第一段" in book.volumes[0].content
        assert book.volumes[0].content == "这是第一卷的第一段。\n\n这是第一卷的第二段。"
        assert book.volumes[1].title == "第二卷"

    def test_parse_volumes_preserve_paragraph_boundaries(self):
        """测试段落之间使用双换行分隔。"""
        html = """
        <html>
        <body>
            <h2><span class="mw-headline" id="第一卷">第一卷</span></h2>
            <p>第一段第一行<br />第一段第二行</p>
            <p>第二段</p>
        </body>
        </html>
        """
        book = Book(title="测试书籍")
        self.parser._parse_volumes(__import__("bs4").BeautifulSoup(html, "html.parser"), book)

        assert book.volumes[0].content == "第一段第一行\n第一段第二行\n\n第二段"

    def test_book_to_dict(self):
        """测试 Book.to_dict() 方法"""
        book = Book(title="测试书籍")
        book.info.name = "测试书籍名"
        book.info.volumes_count = "3"
        book.volumes.append(BookVolume(title="第一卷", content="内容1"))
        book.volumes.append(BookVolume(title="第二卷", content="内容2"))

        result = book.to_dict()

        assert result["title"] == "测试书籍"
        assert result["info"]["名称"] == "测试书籍名"
        assert result["info"]["卷数"] == "3"
        assert len(result["volumes"]) == 2
        assert result["volumes"][0]["title"] == "第一卷"

    def test_skip_navigation_headlines(self):
        """测试跳过导航类标题"""
        html = """
        <html>
        <body>
            <h2><span class="mw-headline" id="目录">目录</span></h2>
            <h2><span class="mw-headline" id="第一卷">第一卷</span></h2>
            <p>内容</p>
            <h2><span class="mw-headline" id="参考资料">参考资料</span></h2>
        </body>
        </html>
        """
        book = Book(title="测试书籍")
        self.parser._parse_volumes(
            __import__("bs4").BeautifulSoup(html, "html.parser"),
            book
        )

        # 应该跳过目录和参考资料
        assert len(book.volumes) == 1
        assert book.volumes[0].title == "第一卷"
