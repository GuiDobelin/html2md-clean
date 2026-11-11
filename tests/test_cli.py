import io
import sys

import pytest

from html2md_clean import __version__, cli
from html2md_clean.fetch import FetchError, Response

PAGE = """<html><head><title>Hello "world"</title></head><body>
<nav><a href="/">Home</a></nav>
<article><h2>Intro</h2><p>See <a href="docs/">the docs</a> <img src="a.png" alt="A">.</p></article>
</body></html>"""


class FakeStdin:
    def __init__(self, data: bytes, tty: bool = False) -> None:
        self.buffer = io.BytesIO(data)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture
def page_file(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(PAGE, encoding="utf-8")
    return path


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_converts_a_file(page_file, capsys):
    assert cli.main([str(page_file)]) == 0
    assert capsys.readouterr().out == "## Intro\n\nSee [the docs](docs/) ![A](a.png).\n"


def test_options(page_file, capsys):
    argv = [str(page_file), "--base-url", "https://e.com/x/", "--no-images", "--title", "--full"]
    assert cli.main(argv) == 0
    assert capsys.readouterr().out == (
        '# Hello "world"\n\n[Home](https://e.com/)\n\n## Intro\n\n'
        "See [the docs](https://e.com/x/docs/) .\n"
    )
    assert cli.main([str(page_file), "--no-links"]) == 0
    assert capsys.readouterr().out == "## Intro\n\nSee the docs ![A](a.png).\n"


def test_title_is_not_repeated(tmp_path, capsys):
    path = tmp_path / "p.html"
    path.write_text("<title>T</title><h1>T</h1><p>x</p>", encoding="utf-8")
    assert cli.main([str(path), "--title"]) == 0
    assert capsys.readouterr().out == "# T\n\nx\n"


def test_front_matter(page_file, capsys):
    assert cli.main([str(page_file), "--front-matter"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(
        f'---\ntitle: "Hello \\"world\\""\nsource: "{page_file}"\n---\n\n## Intro'
    )


def test_reads_stdin_and_writes_output_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "stdin", FakeStdin("<p>café – ok</p>".encode()))
    out = tmp_path / "out.md"
    assert cli.main(["-", "-o", str(out), "--front-matter"]) == 0
    assert (
        out.read_text(encoding="utf-8") == '---\ntitle: null\nsource: "stdin"\n---\n\ncafé – ok\n'
    )
    assert capsys.readouterr().out == ""


def test_no_input_on_a_terminal_is_a_usage_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", FakeStdin(b"", tty=True))
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2
    assert "no input" in capsys.readouterr().err


def test_fetches_urls_and_resolves_links_against_the_final_url(monkeypatch, capsys):
    calls = []

    def fake_fetch(url, timeout):
        calls.append((url, timeout))
        body = '<meta charset="cp1252"><p><a href="next">Caf\xe9</a></p>'.encode("cp1252")
        return Response(url="https://e.com/blog/", content_type="text/html", body=body)

    monkeypatch.setattr(cli, "fetch", fake_fetch)
    assert cli.main(["HTTPS://e.com/old", "--timeout", "5"]) == 0
    assert capsys.readouterr().out == "[Café](https://e.com/blog/next)\n"
    assert calls == [("HTTPS://e.com/old", 5.0)]


def test_fetch_errors_are_reported_without_traceback(monkeypatch, capsys):
    def failing_fetch(url, timeout):
        raise FetchError("HTTP 404 Not Found: https://e.com/")

    monkeypatch.setattr(cli, "fetch", failing_fetch)
    assert cli.main(["https://e.com/"]) == 1
    assert capsys.readouterr().err == "error: HTTP 404 Not Found: https://e.com/\n"


def test_other_url_schemes_are_refused(capsys):
    assert cli.main(["ftp://e.com/x"]) == 1
    assert "only http and https" in capsys.readouterr().err


def test_missing_file_and_unwritable_output(tmp_path, page_file, capsys):
    assert cli.main([str(tmp_path / "missing.html")]) == 1
    assert capsys.readouterr().err.startswith("error: ")
    assert cli.main([str(page_file), "-o", str(tmp_path / "no" / "dir.md")]) == 1
    assert capsys.readouterr().err.startswith("error: ")


def test_empty_result_warns(tmp_path, capsys):
    path = tmp_path / "empty.html"
    path.write_text("<nav>only chrome</nav>", encoding="utf-8")
    assert cli.main([str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no content found" in captured.err


@pytest.mark.parametrize("value", ["0", "-1", "nan"])
def test_timeout_must_be_positive(value, page_file, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([str(page_file), "--timeout", value])
    assert exc.value.code == 2
