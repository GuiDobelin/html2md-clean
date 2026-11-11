"""Decode HTML bytes to text the way browsers pick the encoding."""

from __future__ import annotations

import codecs
import re

__all__ = ["decode_html"]

_BOMS = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
# The WHATWG Encoding Standard decodes ASCII and ISO-8859-1 as windows-1252, and so do browsers.
# Compared by codec name, so every alias (latin_1, cp819, iso-ir-100, ...) is covered.
_WINDOWS_1252 = frozenset({"ascii", "iso8859-1"})
_META_CHARSET = re.compile(
    rb"""<meta[^>]+?charset\s*=\s*["']?\s*([A-Za-z0-9._:-]+)""",
    re.I,
)
_HEADER_CHARSET = re.compile(r"""charset\s*=\s*["']?\s*([A-Za-z0-9._:-]+)""", re.I)


def _codec(label: str | None) -> str | None:
    if not label:
        return None
    try:
        info = codecs.lookup(label.strip())
    except LookupError:
        return None
    # Binary-to-binary and str-to-str codecs such as base64 or rot13 are not text encodings.
    # bytes.decode() refuses them using this same flag.
    if not getattr(info, "_is_text_encoding", True):
        return None
    return "cp1252" if info.name in _WINDOWS_1252 else info.name


def decode_html(data: bytes, content_type: str | None = None) -> str:
    """Decode an HTML document.

    The encoding comes from, in order: a byte order mark, the charset of the HTTP
    ``Content-Type`` header, a ``<meta charset>`` declaration in the first 4 KiB, and finally
    UTF-8. Undecodable bytes become U+FFFD instead of raising.
    """
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            return data[len(bom) :].decode(encoding, errors="replace")
    encoding = None
    if content_type and (match := _HEADER_CHARSET.search(content_type)):
        encoding = _codec(match[1])
    if encoding is None and (match := _META_CHARSET.search(data[:4096])):
        encoding = _codec(match[1].decode("ascii"))
        # A document that is readable as ASCII to find its <meta> cannot be UTF-16 or UTF-32;
        # browsers read such a declaration as UTF-8.
        if encoding and encoding.startswith(("utf_16", "utf_32", "utf-16", "utf-32")):
            encoding = "utf-8"
    return data.decode(encoding or "utf-8", errors="replace")
