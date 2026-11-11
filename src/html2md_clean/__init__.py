"""Convert web pages into clean Markdown without boilerplate, using only the standard library."""

from html2md_clean.convert import Page, convert, html_to_markdown
from html2md_clean.decode import decode_html

__version__ = "0.1.0"

__all__ = ["Page", "__version__", "convert", "decode_html", "html_to_markdown"]
