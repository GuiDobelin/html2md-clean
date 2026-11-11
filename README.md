# html2md-clean

**Convert web pages into clean Markdown: the article, not the menu.**

[![CI](https://github.com/GuiDobelin/html2md-clean/actions/workflows/ci.yml/badge.svg)](https://github.com/GuiDobelin/html2md-clean/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Feeding web pages to an LLM, a RAG index or a notes app works much better with Markdown than
with raw HTML, but naive converters keep everything: the navigation bar, the cookie banner, the
share buttons, the "related posts" sidebar and the footer. `html2md-clean` keeps the main
content and turns it into readable [CommonMark](https://commonmark.org/) with GitHub tables:

- **Finds the content**: the largest `<main>`, else the top-level `<article>` elements, else the
  page; it falls back to the next choice if one turns out to hold only chrome.
- **Drops page chrome**: `nav`, `aside`, page-level `header`/`footer`, ARIA landmarks such as
  `role="navigation"`, hidden elements, and elements named like chrome (`cookie-banner`,
  `share-buttons`, `sidebar`, `comments` and similar). Wrappers holding most of the text are never
  dropped by name, and code blocks are left alone so highlighter classes like `token comment`
  survive.
- **Keeps structure**: headings, nested and numbered lists, links (made absolute), images
  (including lazy-loaded ones), fenced code with its language, block quotes, tables and line
  breaks, with Markdown characters in the text escaped.
- **Decodes like a browser**: byte order mark, then the HTTP charset, then `<meta charset>`,
  with ISO-8859-1 read as windows-1252.
- **Has no dependencies**: only the Python standard library. Fetching URLs is included, with a
  size limit, a content-type check and redirects limited to http(s).

## Install

```bash
pip install "git+https://github.com/GuiDobelin/html2md-clean"
```

## Usage

### CLI

Pass a file, an `http(s)` URL, or pipe HTML into standard input:

```bash
html2md-clean https://example.com/blog/post > post.md
curl -s https://example.com/blog/post | html2md-clean --base-url https://example.com/blog/post
```

Converting [`examples/article.html`](examples/article.html), a blog post with a navigation bar,
a cookie banner, share buttons, comments, a sidebar and a footer:

````text
$ html2md-clean examples/article.html --base-url https://blog.example.com/posts/chunking/
# Chunking strategies for RAG

By [Ana Souza](https://blog.example.com/authors/ana/) · 6 min read

Retrieval quality depends on **how you split documents** before embedding them. Chunks that are too small lose context; chunks that are too large dilute the match.

## Three common approaches

1. **Fixed size** with overlap, e.g. 800 characters and 120 of overlap.
2. **Recursive** splitting on paragraphs, then sentences.
3. **Semantic** splitting where the topic changes.

```python
def chunk(text, size=800, overlap=120):
    # Slide a window over the text.
    step = size - overlap
    return [text[i:i + size] for i in range(0, len(text), step)]
```

| Strategy | Recall@5 | Index size |
| --- | --- | --- |
| Fixed | 0.71 | 1.0× |
| Recursive | 0.78 | 1.1× |

> Measure on your own questions before picking one.

![Recall by chunk size](https://blog.example.com/img/recall.png)
````

`--front-matter` adds the title and source for indexing pipelines, and `--no-links` /
`--no-images` keep only the text:

```text
$ html2md-clean examples/article.html --front-matter --no-links --no-images | head -6
---
title: "Chunking strategies for RAG | Example Engineering Blog"
source: "examples/article.html"
---

# Chunking strategies for RAG
```

Use `--full` to convert the whole page, chrome included, and `--title` to start the output
with the page title when the content has no `#` heading of its own.

```text
$ html2md-clean --help
usage: html2md-clean [-h] [-o OUTPUT] [--base-url BASE_URL] [--full]
                     [--no-links] [--no-images] [--title] [--front-matter]
                     [--timeout TIMEOUT] [--version]
                     [source]

Convert a web page into clean Markdown: keep the main content, drop
navigation, banners and other page chrome.

positional arguments:
  source                an HTML file, an http(s) URL, or - to read standard
                        input (the default)

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        write to this file (default: stdout)
  --base-url BASE_URL   resolve relative links and images against this URL
                        (default: the fetched URL)
  --full                convert the whole page, including page chrome
  --no-links            keep link text, drop the URLs
  --no-images           leave images out
  --title               start with the page title as a # heading
  --front-matter        start with YAML front matter holding the title and
                        source
  --timeout TIMEOUT     seconds to wait for a URL (default: 20)
  --version             show program's version number and exit
```

### Python

```python
from pathlib import Path

from html2md_clean import convert, decode_html, html_to_markdown

page = convert(
    decode_html(Path("examples/article.html").read_bytes()),
    base_url="https://blog.example.com/posts/chunking/",
)
print(page.title)  # Chunking strategies for RAG | Example Engineering Blog
print(page.markdown.splitlines()[0])  # # Chunking strategies for RAG

html_to_markdown("<p>Hello <b>world</b></p>")  # 'Hello **world**'
```

`convert()` takes the options `base_url`, `full`, `links` and `images`, and returns a `Page`
with `title` and `markdown`. `decode_html(data, content_type=None)` turns raw bytes into text,
and `html2md_clean.fetch.fetch(url)` downloads a page.

## Limitations

- Content is chosen with HTML structure and naming heuristics, not with a readability score.
  Pages that put everything in anonymous `<div>`s keep more noise; use `--full` when a page is
  trimmed too much.
- JavaScript is not run, so pages that build their content in the browser come out empty.
- `fetch` is meant for a command-line tool run by the user: it does not block private network
  addresses. Do not call it with untrusted URLs on a server.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

## Ecosystem

Part of a set of small tools around [citerag](https://github.com/GuiDobelin/citerag), a self-hostable
RAG API that answers questions about your documents with verifiable citations. `html2md-clean`
grew out of citerag's URL loader and is handy for preparing web pages before ingesting them.

## License

[MIT](LICENSE)
