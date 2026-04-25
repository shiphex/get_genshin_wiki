"""Books content package."""

from .parser import Book, BookInfo, BookParser, BookVolume
from .writer import BookStorage

__all__ = ["Book", "BookInfo", "BookParser", "BookStorage", "BookVolume"]
