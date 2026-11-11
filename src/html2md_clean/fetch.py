"""Download a web page with the standard library."""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from html2md_clean import __version__

__all__ = ["FetchError", "Response", "fetch"]

DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml", "text/plain"})
_CHUNK = 64 * 1024


class FetchError(Exception):
    """The page could not be downloaded, or is not an HTML page."""


@dataclass(frozen=True)
class Response:
    url: str
    """The final URL, after redirects. Relative links resolve against it."""
    content_type: str | None
    body: bytes


def _check_scheme(url: str) -> None:
    if urlsplit(url).scheme.lower() not in ("http", "https"):
        raise FetchError(f"only http and https URLs are supported: {url}")


class _HTTPOnlyRedirects(urllib.request.HTTPRedirectHandler):
    # urllib follows redirects to ftp:// as well; a web page should never lead there.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_scheme(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_HTTPOnlyRedirects)


def fetch(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    opener: urllib.request.OpenerDirector | None = None,
) -> Response:
    """Download ``url`` and return its body, content type and final URL.

    Raises:
        FetchError: for non-HTTP URLs, network errors, HTTP error statuses, bodies larger than
            ``max_bytes`` and content types that are not HTML or plain text.
    """
    _check_scheme(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"html2md-clean/{__version__} (+https://github.com/GuiDobelin/html2md-clean)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5",
        },
    )
    try:
        with (opener or _default_opener()).open(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type")
            media_type = (content_type or "").split(";", 1)[0].strip().lower()
            if media_type and media_type not in _HTML_TYPES:
                raise FetchError(f"not an HTML page ({media_type}): {url}")
            chunks: list[bytes] = []
            size = 0
            while chunk := response.read(_CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise FetchError(f"page is larger than {max_bytes} bytes: {url}")
                chunks.append(chunk)
            return Response(url=response.geturl(), content_type=content_type, body=b"".join(chunks))
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} {exc.reason}: {url}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"could not fetch {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise FetchError(f"timed out after {timeout:g}s: {url}") from exc
    except ValueError as exc:
        raise FetchError(f"invalid URL {url}: {exc}") from exc
