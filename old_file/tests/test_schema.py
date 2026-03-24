"""Tests for schema models."""

import pytest
from datetime import datetime
from src.schema.models import WikiPage, Infobox, Revision, PageListItem


class TestWikiPage:
    """Test cases for WikiPage model."""

    def test_create_page(self):
        """Test creating a WikiPage."""
        page = WikiPage(
            id=123,
            title="Test Page",
            url="https://example.com/wiki/Test_Page",
            namespace=0,
        )
        assert page.id == 123
        assert page.title == "Test Page"
        assert page.namespace == 0
        assert page.source == "mediawiki"

    def test_to_dict(self):
        """Test converting to dictionary."""
        page = WikiPage(
            id=123,
            title="Test Page",
            url="https://example.com/wiki/Test_Page",
            namespace=0,
        )
        data = page.to_dict()
        assert data["id"] == 123
        assert data["title"] == "Test Page"
        assert data["url"] == "https://example.com/wiki/Test_Page"
        assert "fetched_at" in data

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "id": 123,
            "title": "Test Page",
            "url": "https://example.com/wiki/Test_Page",
            "namespace": 0,
            "content_raw": "Test content",
            "categories": ["Category:Test"],
            "links": ["Link1", "Link2"],
            "templates": ["Template1"],
        }
        page = WikiPage.from_dict(data)
        assert page.id == 123
        assert page.title == "Test Page"
        assert page.content_raw == "Test content"
        assert page.categories == ["Category:Test"]

    def test_with_infobox(self):
        """Test WikiPage with Infobox."""
        infobox = Infobox(
            template_name="角色",
            data={"name": "Test", "rarity": "5"},
            raw_template="{{角色|...}}",
        )
        page = WikiPage(
            id=123,
            title="Test Page",
            url="https://example.com/wiki/Test_Page",
            namespace=0,
            infobox=infobox,
        )
        data = page.to_dict()
        assert data["infobox"]["template_name"] == "角色"
        assert data["infobox"]["data"]["name"] == "Test"

    def test_with_revision(self):
        """Test WikiPage with Revision."""
        revision = Revision(
            rev_id=456,
            parent_id=455,
            timestamp="2024-01-01T00:00:00Z",
            user="TestUser",
            content_model="wikitext",
            content_format="text/x-wiki",
        )
        page = WikiPage(
            id=123,
            title="Test Page",
            url="https://example.com/wiki/Test_Page",
            namespace=0,
            revision=revision,
        )
        data = page.to_dict()
        assert data["revision"]["rev_id"] == 456
        assert data["revision"]["user"] == "TestUser"


class TestInfobox:
    """Test cases for Infobox model."""

    def test_create_infobox(self):
        """Test creating an Infobox."""
        infobox = Infobox(
            template_name="角色",
            data={"name": "甘雨", "rarity": "5"},
            raw_template="{{角色|...}}",
        )
        assert infobox.template_name == "角色"
        assert infobox.data["name"] == "甘雨"

    def test_infobox_to_dict(self):
        """Test Infobox to dict."""
        infobox = Infobox(
            template_name="角色",
            data={"name": "Test"},
        )
        data = infobox.to_dict()
        assert data["template_name"] == "角色"
        assert data["data"]["name"] == "Test"


class TestRevision:
    """Test cases for Revision model."""

    def test_create_revision(self):
        """Test creating a Revision."""
        revision = Revision(
            rev_id=456,
            parent_id=455,
            timestamp="2024-01-01T00:00:00Z",
            user="TestUser",
            content_model="wikitext",
            content_format="text/x-wiki",
        )
        assert revision.rev_id == 456
        assert revision.user == "TestUser"


class TestPageListItem:
    """Test cases for PageListItem model."""

    def test_create_page_list_item(self):
        """Test creating a PageListItem."""
        item = PageListItem(
            page_id=123,
            title="Test Page",
            namespace=0,
            redirect=False,
        )
        assert item.page_id == 123
        assert item.title == "Test Page"
        assert not item.redirect
