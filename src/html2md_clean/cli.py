import argparse
import contextlib
import html
import json
import math
import os
import sys
from pathlib import Path

from html2md_clean import __version__
from html2md_clean.convert import convert, html_to_markdown
from html2md_clean.decode import decode_html
from html2md_clean.fetch import DEFAULT_TIMEOUT, FetchError, fetch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="html2md-clean",
        description=(
            "Convert a web page into clean Markdown: keep the main content, drop navigation, "
            "banners and other page chrome."
        ),
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="an HTML file, an http(s) URL, or - to read standard input (the default)",
    )
    parser.add_argument("-o", "--output", default="-", help="write to this file (default: stdout)")
    parser.add_argument(
        "--base-url",
        help="resolve relative links and images against this URL (default: the fetched URL)",
    )
    parser.add_argument(
        "--full", action="store_true", help="convert the whole page, including page chrome"
    )
    parser.add_argument("--no-links", action="store_true", help="keep link text, drop the URLs")
    parser.add_argument("--no-images", action="store_true", help="leave images out")
    parser.add_argument(
        "--title", action="store_true", help="start with the page title as a # heading"
    )
    parser.add_argument(
        "--front-matter",
        action="store_true",
        help="start with YAML front matter holding the title and source",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"seconds allowed to download a URL (default: {DEFAULT_TIMEOUT:g})",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _read(source: str, timeout: float) -> tuple[str, str | None]:
    """Return the decoded HTML and the URL it came from, if any."""
    if source.lower().startswith(("http://", "https://")):
        response = fetch(source, timeout=timeout)
        return decode_html(response.body, response.content_type), response.url
    if "://" in source:
        raise FetchError(f"only http and https URLs are supported: {source}")
    if source == "-":
        return decode_html(sys.stdin.buffer.read()), None
    return decode_html(Path(source).read_bytes()), None


def _write(text: str, output: str) -> None:
    if output == "-":
        try:
            sys.stdout.buffer.write(text.encode("utf-8"))
            sys.stdout.buffer.flush()
        except BrokenPipeError:
            # The reader (e.g. `| head`) is gone, which is not an error. Point stdout at devnull
            # so the flush at interpreter exit does not complain again.
            with contextlib.suppress(OSError, ValueError, AttributeError):
                os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    else:
        Path(output).write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not (args.timeout > 0 and math.isfinite(args.timeout)):
        parser.error("--timeout must be a positive number")
    if args.source is None:
        # An explicit "-" may be typed or pasted at a terminal; no argument at all is a mistake.
        if sys.stdin is None or sys.stdin.isatty():
            parser.error("no input: pass an HTML file or URL, or pipe HTML into standard input")
        args.source = "-"

    try:
        document, fetched_url = _read(args.source, args.timeout)
    except (FetchError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    page = convert(
        document,
        base_url=args.base_url or fetched_url,
        full=args.full,
        links=not args.no_links,
        images=not args.no_images,
    )
    if not page.markdown:
        print("warning: no content found", file=sys.stderr)

    parts = []
    if args.front_matter:
        source = fetched_url or ("stdin" if args.source == "-" else args.source)
        parts.append(
            "---\n"
            f"title: {json.dumps(page.title, ensure_ascii=False)}\n"
            f"source: {json.dumps(source, ensure_ascii=False)}\n"
            "---"
        )
    if args.title and page.title and not page.markdown.startswith("# "):
        parts.append(html_to_markdown(f"<h1>{html.escape(page.title)}</h1>"))
    if page.markdown:
        parts.append(page.markdown)
    try:
        _write("\n\n".join(parts) + "\n" if parts else "", args.output)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
