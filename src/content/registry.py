"""Namespace registry for content types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.content.arms.parser import ArmsParser
from src.content.arms.validator import ArmsValidator
from src.content.arms.writer import ArmStorage
from src.content.artifacts.parser import ArtifactsParser
from src.content.artifacts.validator import ArtifactsValidator
from src.content.artifacts.writer import ArtifactStorage
from src.content.books.parser import BookParser
from src.content.books.validator import BookValidator
from src.content.books.writer import BookStorage


@dataclass(frozen=True, slots=True)
class ContentSpec:
    """Runtime metadata for a content namespace."""

    namespace: str
    page_title: str
    parser_class: type
    validator_class: type
    writer_class: type
    list_extractor: str
    detail_parser: str
    crawl_script: str

    def create_parser(self, base_url: str) -> Any:
        return self.parser_class(base_url=base_url)

    def create_validator(self) -> Any:
        return self.validator_class()

    def create_writer(self, storage_config: dict[str, Any]) -> Any:
        return self.writer_class(storage_config=storage_config)

    def extract_links(self, parser: Any, html: str) -> list[dict[str, str]]:
        return getattr(parser, self.list_extractor)(html)

    def parse_detail(self, parser: Any, html: str, title: str, url: str) -> Any:
        return getattr(parser, self.detail_parser)(html, title, url)


CONTENT_SPECS: dict[str, ContentSpec] = {
    "books": ContentSpec("books", "书籍一览", BookParser, BookValidator, BookStorage, "extract_book_links", "parse_book_page", "scripts/crawl_books.py"),
    "arms": ContentSpec("arms", "武器图鉴", ArmsParser, ArmsValidator, ArmStorage, "extract_arm_links", "parse_arm_page", "scripts/crawl_arms.py"),
    "artifacts": ContentSpec("artifacts", "圣遗物图鉴", ArtifactsParser, ArtifactsValidator, ArtifactStorage, "extract_artifact_links", "parse_artifact_page", "scripts/crawl_artifacts.py"),
}


def get_content_spec(namespace: str) -> ContentSpec:
    try:
        return CONTENT_SPECS[namespace]
    except KeyError as exc:
        raise ValueError(f"Unknown namespace: {namespace}") from exc
