"""Content-oriented crawler modules."""

from .registry import CONTENT_SPECS, ContentSpec, get_content_spec

__all__ = ["CONTENT_SPECS", "ContentSpec", "get_content_spec"]
