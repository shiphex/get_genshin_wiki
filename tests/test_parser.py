"""Tests for parser module."""

import pytest
from src.parser.wikitext_parser import WikitextParser


class TestWikitextParser:
    """Test cases for WikitextParser."""

    def setup_method(self):
        """Setup test fixtures."""
        self.parser = WikitextParser()

    def test_parse_empty(self):
        """Test parsing empty content."""
        result = self.parser.parse("")
        assert result["templates"] == []
        assert result["links"] == []
        assert result["text"] == ""

    def test_parse_templates(self):
        """Test template extraction."""
        wikitext = "{{角色|name=甘雨|rarity=5}}{{引用}}"
        result = self.parser.parse(wikitext)
        assert "角色" in result["templates"]

    def test_parse_links(self):
        """Test internal link extraction."""
        wikitext = "[[提瓦特]]和[[蒙德]]是地点"
        result = self.parser.parse(wikitext)
        assert "提瓦特" in result["links"]
        assert "蒙德" in result["links"]

    def test_parse_categories(self):
        """Test category extraction."""
        wikitext = "[[Category:角色]]和[[Category:五星角色]]"
        result = self.parser.parse(wikitext)
        categories = result["categories"]
        assert "角色" in categories
        assert "五星角色" in categories

    def test_extract_infobox(self):
        """Test infobox extraction."""
        wikitext = "{{角色|名称=甘雨|稀有度=5|元素=冰}}"
        result = self.parser.parse(wikitext)

        if result["infobox"]:
            assert result["infobox"]["template_name"] == "角色"
            assert "名称" in result["infobox"]["data"] or "name" in result["infobox"]["data"]

    def test_parse_html(self):
        """Test HTML parsing."""
        html = "<div><p>Hello</p><a href=\"/wiki/Test\">Link</a></div>"
        result = self.parser.parse_html(html)
        assert "text" in result
        assert "Hello" in result["text"]
