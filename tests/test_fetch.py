import http.client
import io
import urllib.error
import urllib.request
from email.message import Message

import pytest

from html2md_clean.fetch import FetchError, _HTTPOnlyRedirects, fetch


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, content_type: str | None, url: str) -> None:
        super().__init__(body)
        self.headers = Message()
        if content_type is not None:
            self.headers["Content-Type"] = content_type
        self._url = url

    def geturl(self) -> str:
        return self._url


class FakeOpener:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[tuple[urllib.request.Request, float]] = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error is not None:
            raise self.error
        return self.response


def test_fetch_returns_body_type_and_final_url():
    opener = FakeOpener(FakeResponse(b"<p>hi</p>", "text/html; charset=utf-8", "https://e.com/b"))
    response = fetch("https://e.com/a", timeout=3, opener=opener)
    assert response.body == b"<p>hi</p>"
    assert response.content_type == "text/html; charset=utf-8"
    assert response.url == "https://e.com/b"
    request, timeout = opener.requests[0]
    assert timeout == 3
    assert request.get_header("User-agent").startswith("html2md-clean/")


@pytest.mark.parametrize("content_type", [None, "TEXT/HTML", "application/xhtml+xml"])
def test_fetch_accepts_html_and_unknown_types(content_type):
    opener = FakeOpener(FakeResponse(b"x", content_type, "https://e.com/"))
    assert fetch("https://e.com/", opener=opener).body == b"x"


def test_fetch_rejects_other_content_types():
    opener = FakeOpener(FakeResponse(b"%PDF", "application/pdf", "https://e.com/f.pdf"))
    with pytest.raises(FetchError, match="not an HTML page"):
        fetch("https://e.com/f.pdf", opener=opener)


def test_fetch_enforces_max_bytes():
    opener = FakeOpener(FakeResponse(b"a" * 200_000, "text/html", "https://e.com/"))
    with pytest.raises(FetchError, match="larger than 100000 bytes"):
        fetch("https://e.com/", max_bytes=100_000, opener=opener)
    exact = FakeOpener(FakeResponse(b"a" * 100_000, "text/html", "https://e.com/"))
    assert len(fetch("https://e.com/", max_bytes=100_000, opener=exact).body) == 100_000


@pytest.mark.parametrize("url", ["ftp://e.com/x", "file:///etc/passwd", "e.com/x"])
def test_fetch_rejects_non_http_urls(url):
    opener = FakeOpener()
    with pytest.raises(FetchError, match="only http and https"):
        fetch(url, opener=opener)
    assert opener.requests == []


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (urllib.error.HTTPError("https://e.com/", 404, "Not Found", Message(), None), "HTTP 404"),
        (urllib.error.URLError("Name or service not known"), "could not fetch"),
        (TimeoutError(), "timed out after 20s"),
        (ValueError("bad port"), "invalid URL"),
    ],
)
def test_fetch_wraps_errors(error, message):
    with pytest.raises(FetchError, match=message):
        fetch("https://e.com/", opener=FakeOpener(error=error))


def test_redirects_to_other_schemes_are_refused():
    handler = _HTTPOnlyRedirects()
    request = urllib.request.Request("https://e.com/")
    with pytest.raises(FetchError, match="only http and https"):
        handler.redirect_request(request, None, 302, "Found", Message(), "ftp://e.com/x")
    redirected = handler.redirect_request(request, None, 302, "Found", Message(), "https://e.com/y")
    assert redirected.full_url == "https://e.com/y"


@pytest.mark.parametrize(
    "error",
    [http.client.IncompleteRead(b"partial", 100), ConnectionResetError("reset by peer")],
)
def test_fetch_wraps_errors_while_reading_the_body(error):
    class Failing(FakeResponse):
        def read1(self, size=-1):
            raise error

    opener = FakeOpener(Failing(b"", "text/html", "https://e.com/"))
    with pytest.raises(FetchError, match="could not fetch"):
        fetch("https://e.com/", opener=opener)


def test_fetch_rejects_plain_text():
    # The converter would treat it as HTML and collapse its line breaks.
    opener = FakeOpener(FakeResponse(b"a\nb", "text/plain", "https://e.com/a.txt"))
    with pytest.raises(FetchError, match="not an HTML page"):
        fetch("https://e.com/a.txt", opener=opener)


def test_timeout_bounds_the_whole_download(monkeypatch):
    clock = iter([0.0, 5.0, 25.0])
    monkeypatch.setattr("html2md_clean.fetch.time.monotonic", lambda: next(clock))

    class Trickle(FakeResponse):
        def read1(self, size=-1):
            return super().read1(1)

    opener = FakeOpener(Trickle(b"abc", "text/html", "https://e.com/"))
    with pytest.raises(FetchError, match="timed out after 20s"):
        fetch("https://e.com/", timeout=20, opener=opener)
