"""Tests for text cleaner module."""

import pytest
from src.cleaner.text_cleaner import TextCleaner


class TestTextCleaner:
    """Test cases for TextCleaner."""

    def setup_method(self):
        """Setup test fixtures."""
        self.cleaner = TextCleaner()

    def test_clean_basic(self):
        """Test basic cleaning."""
        text = "Hello  World\n\n\n\nTest"
        result = self.cleaner.clean(text)
        assert "  " not in result
        assert "\n\n\n\n" not in result

    def test_clean_html_tags(self):
        """Test HTML tag removal."""
        text = "<p>Hello</p><br/><div>World</div>"
        result = self.cleaner.clean(text)
        assert "<" not in result
        assert ">" not in result
        assert "Hello" in result
        assert "World" in result

    def test_clean_footnotes(self):
        """Test footnote removal."""
        text = "Text with ref[1] and <ref>citation</ref>"
        result = self.cleaner.clean(text)
        assert "[1]" not in result
        assert "citation" not in result

    def test_clean_wiki_links(self):
        """Test wiki link cleaning."""
        text = "[[Page Title|Display Text]] and [[Another Page]]"
        result = self.cleaner.clean(text)
        assert "[[" not in result
        assert "]]" not in result
        assert "Display Text" in result
        assert "Another Page" in result

    def test_clean_external_links(self):
        """Test external link cleaning."""
        text = "Check [https://example.com link] and [http://test.org]"
        result = self.cleaner.clean(text)
        assert "https://" not in result
        assert "http://" not in result
        assert "link" in result

    def test_normalize_categories(self):
        """Test category normalization."""
        categories = ["Category:角色", "角色", "Category:NPC", "npc"]
        result = self.cleaner.normalize_categories(categories)
        assert len(result) == 2  # Should deduplicate
        assert "角色" in result
        assert "NPC" in result

    def test_normalize_links(self):
        """Test link normalization."""
        links = ["Page One", "Page One#Section", "Page Two", ":Page Three"]
        result = self.cleaner.normalize_links(links)
        # Should remove anchor and deduplicate
        assert "Page One" in result
        assert "Page Two" in result
        # : prefix should be filtered
        assert ":Page Three" not in result

    def test_remove_duplicates(self):
        """Test duplicate removal."""
        items = ["Item", "item", "ITEM", "Different"]
        result = self.cleaner.remove_duplicates(items)
        assert len(result) == 2
        assert "Item" in result
        assert "Different" in result

    def test_empty_text(self):
        """Test empty text handling."""
        result = self.cleaner.clean("")
        assert result == ""

    def test_none_text(self):
        """Test None text handling."""
        result = self.cleaner.clean(None)
        assert result == ""
