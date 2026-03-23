"""Data schema definitions for MediaWiki pages."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Revision:
    """Page revision information."""
    rev_id: int
    parent_id: int
    timestamp: str
    user: str
    content_model: str
    content_format: str
    comment: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "rev_id": self.rev_id,
            "parent_id": self.parent_id,
            "timestamp": self.timestamp,
            "user": self.user,
            "content_model": self.content_model,
            "content_format": self.content_format,
            "comment": self.comment,
        }


@dataclass
class Infobox:
    """Infobox extracted from page."""
    template_name: str
    data: dict = field(default_factory=dict)
    raw_template: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "template_name": self.template_name,
            "data": self.data,
            "raw_template": self.raw_template,
        }


@dataclass
class WikiPage:
    """Main data model for a MediaWiki page."""
    id: int
    title: str
    url: str
    namespace: int
    source: str = "mediawiki"
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Content
    content_raw: str = ""
    content_clean: str = ""

    # Metadata
    categories: list = field(default_factory=list)
    links: list = field(default_factory=list)
    templates: list = field(default_factory=list)
    infobox: Optional[Infobox] = None
    revision: Optional[Revision] = None

    # Page info
    page_id: int = 0
    last_modified: Optional[str] = None
    redirect: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "namespace": self.namespace,
            "source": self.source,
            "fetched_at": self.fetched_at,
            "content_raw": self.content_raw,
            "content_clean": self.content_clean,
            "categories": self.categories,
            "links": self.links,
            "templates": self.templates,
            "infobox": self.infobox.to_dict() if self.infobox else {},
            "revision": self.revision.to_dict() if self.revision else {},
            "page_id": self.page_id,
            "last_modified": self.last_modified,
            "redirect": self.redirect,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WikiPage":
        """Create from dictionary."""
        infobox_data = data.get("infobox", {})
        if infobox_data:
            infobox = Infobox(
                template_name=infobox_data.get("template_name", ""),
                data=infobox_data.get("data", {}),
                raw_template=infobox_data.get("raw_template", ""),
            )
        else:
            infobox = None

        revision_data = data.get("revision", {})
        if revision_data:
            revision = Revision(
                rev_id=revision_data.get("rev_id", 0),
                parent_id=revision_data.get("parent_id", 0),
                timestamp=revision_data.get("timestamp", ""),
                user=revision_data.get("user", ""),
                content_model=revision_data.get("content_model", ""),
                content_format=revision_data.get("content_format", ""),
                comment=revision_data.get("comment"),
            )
        else:
            revision = None

        return cls(
            id=data.get("id", 0),
            title=data.get("title", ""),
            url=data.get("url", ""),
            namespace=data.get("namespace", 0),
            source=data.get("source", "mediawiki"),
            fetched_at=data.get("fetched_at", ""),
            content_raw=data.get("content_raw", ""),
            content_clean=data.get("content_clean", ""),
            categories=data.get("categories", []),
            links=data.get("links", []),
            templates=data.get("templates", []),
            infobox=infobox,
            revision=revision,
            page_id=data.get("page_id", 0),
            last_modified=data.get("last_modified"),
            redirect=data.get("redirect"),
        )


@dataclass
class CategoryInfo:
    """Category information."""
    id: int
    title: str
    page_count: int
    subcategories: list = field(default_factory=list)
    members: list = field(default_factory=list)


@dataclass
class PageListItem:
    """Item in page list (from category members, search, etc.)."""
    page_id: int
    title: str
    namespace: int
    redirect: bool = False
