"""Turn an HTML page into clean Markdown.

The conversion has three steps:

1. Parse the HTML into a small tree with a forgiving, standard-library parser that applies the
   most common implicit end-tag rules of the HTML spec (``<p>``, ``<li>``, table cells, ...).
2. Pick the content: the largest ``<main>``, else the top-level ``<article>`` elements, else the
   whole page, and remove page chrome inside it (navigation, cookie banners, share buttons,
   hidden elements, ...). ``full=True`` keeps everything except non-content elements such as
   scripts and styles.
3. Render the tree as CommonMark with GitHub tables and strikethrough.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

__all__ = ["Page", "convert", "html_to_markdown"]

# Deeper elements are flattened into their ancestor, which keeps rendering recursion bounded.
MAX_DEPTH = 200

_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
# Never readable content, whatever the mode.
_NON_CONTENT = frozenset(
    {
        "head",
        # <head> is optional in HTML, so <title> can appear without one.
        "title",
        "script",
        "style",
        "template",
        "noscript",
        "svg",
        "math",
        "canvas",
        "iframe",
        "object",
        "embed",
        "video",
        "audio",
        "map",
        "select",
        "input",
        "textarea",
        "button",
    }
)
_CHROME_TAGS = frozenset({"nav", "aside", "dialog"})
_CHROME_ROLES = frozenset(
    {
        "navigation",
        "banner",
        "contentinfo",
        "complementary",
        "search",
        "dialog",
        "alertdialog",
        "menu",
        "menubar",
        "toolbar",
    }
)
# Words in class names and ids that mark page chrome. Matched against whole words of the name,
# so "nav" matches "main-nav" and "mainNav" but not "canvas".
_CHROME_WORDS = frozenset(
    {
        "ad",
        "ads",
        "advert",
        "advertisement",
        "banner",
        "breadcrumb",
        "breadcrumbs",
        "comment",
        "comments",
        "consent",
        "cookie",
        "cookies",
        "gdpr",
        "menu",
        "modal",
        "nav",
        "navbar",
        "navigation",
        "newsletter",
        "popup",
        "promo",
        "related",
        "share",
        "sharing",
        "sidebar",
        "skip",
        "social",
        "sponsor",
        "sponsored",
        "subscribe",
    }
)
# Layout modifiers such as "has-sidebar" describe the element's surroundings, not the element.
_MODIFIER_WORDS = frozenset({"has", "with", "no", "without"})
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
_SECTIONING = frozenset({"main", "article", "section"})
_NEVER_GUESS = frozenset({"html", "body", "main", "article"})
_CODE = frozenset({"pre", "code", "kbd", "samp", "tt"})

_HEADINGS = {f"h{n}": n for n in range(1, 7)}
_BLOCK = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "caption",
        "center",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "header",
        "hgroup",
        "hr",
        "html",
        "li",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
        *_HEADINGS,
    }
)

# Opening any of these closes an open <p>, as in the HTML spec.
_CLOSES_P = (_BLOCK - {"body", "html", "caption", "td", "th", "tr", "tbody", "thead", "tfoot"}) | {
    "li",
    "dd",
    "dt",
}
# Implicit closes and stray end tags do not reach past these elements.
_SCOPE = frozenset({"table", "td", "th", "caption", "button", "template", "html"})
_TABLE_PARTS = frozenset({"table", "caption", "thead", "tbody", "tfoot", "tr", "td", "th"})


@dataclass(frozen=True)
class Page:
    """A converted page: its title (if the HTML has one) and the Markdown body."""

    title: str | None
    markdown: str


class _Node:
    __slots__ = ("tag", "attrs", "children", "block", "_text_len")

    def __init__(self, tag: str, attrs: dict[str, str]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[_Node | str] = []
        self.block = False
        self._text_len: int | None = None


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#document", {})
        self._stack = [self.root]
        # Tags opened past MAX_DEPTH, which were not pushed and must not close real elements.
        self._overflow: list[str] = []

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag, attrs):
        # HTML ignores "/>" on non-void elements, but pages that use it are XHTML-style and
        # mean an empty element. Keeping it open would swallow the rest of the page.
        self._open(tag, attrs, self_closing=True)

    def handle_endtag(self, tag):
        if tag in self._overflow:
            del self._overflow[len(self._overflow) - 1 - self._overflow[::-1].index(tag)]
            return
        stack = self._stack
        for i in range(len(stack) - 1, 0, -1):
            current = stack[i].tag
            if current == tag:
                del stack[i:]
                return
            if current in _SCOPE and tag not in _TABLE_PARTS:
                return

    def handle_data(self, data):
        self._stack[-1].children.append(data)

    def _open(self, tag: str, attrs, self_closing: bool) -> None:
        self._close_implied(tag)
        node = _Node(tag, {name: value or "" for name, value in reversed(attrs)})
        self._stack[-1].children.append(node)
        if tag in _VOID or self_closing:
            return
        if len(self._stack) > MAX_DEPTH:
            self._overflow.append(tag)
            return
        self._stack.append(node)

    def _close_implied(self, tag: str) -> None:
        if tag in _CLOSES_P:
            self._close("p", _SCOPE)
        if tag == "li":
            self._close("li", _SCOPE | {"ul", "ol", "menu"})
        elif tag in ("dt", "dd"):
            self._close({"dt", "dd"}, _SCOPE | {"dl"})
        elif tag == "tr":
            self._close("tr", {"table", "thead", "tbody", "tfoot"})
        elif tag in ("td", "th"):
            self._close({"td", "th"}, {"table", "tr"})
        elif tag in ("thead", "tbody", "tfoot"):
            self._close({"thead", "tbody", "tfoot"}, {"table"})
        elif tag == "a":
            self._close("a", _SCOPE)

    def _close(self, names: str | set[str], boundaries: frozenset[str] | set[str]) -> None:
        names = {names} if isinstance(names, str) else names
        stack = self._stack
        for i in range(len(stack) - 1, 0, -1):
            current = stack[i].tag
            if current in names:
                del stack[i:]
                return
            if current in boundaries:
                return


def _elements(node: _Node):
    return (child for child in node.children if isinstance(child, _Node))


def _is_hidden(node: _Node) -> bool:
    attrs = node.attrs
    # hidden="until-found" content is collapsed but findable, e.g. folded sections.
    if "hidden" in attrs and attrs["hidden"].lower() != "until-found":
        return True
    if attrs.get("aria-hidden", "").strip().lower() == "true":
        return True
    return bool(_HIDDEN_STYLE.search(attrs.get("style", "")))


def _text_len(node: _Node) -> int:
    """Count the visible non-whitespace characters under ``node``."""
    if node._text_len is None:
        if node.tag in _NON_CONTENT or _is_hidden(node):
            node._text_len = 0
        else:
            node._text_len = sum(
                len("".join(child.split())) if isinstance(child, str) else _text_len(child)
                for child in node.children
            )
    return node._text_len


def _words(name: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", name)]


def _named_like_chrome(node: _Node) -> bool:
    names = f"{node.attrs.get('class', '')} {node.attrs.get('id', '')}".split()
    for name in names:
        words = _words(name)
        if not _MODIFIER_WORDS.intersection(words) and _CHROME_WORDS.intersection(words):
            return True
    return False


def _contains(node: _Node, tags: frozenset[str]) -> bool:
    return any(child.tag in tags or _contains(child, tags) for child in _elements(node))


def _holds_content(node: _Node, root_len: int) -> bool:
    # Guards the class-name guess: a wrapper named "sidebar-layout" may hold the whole article.
    # Containing an <article> is not enough: comment lists mark up each comment as one.
    return 2 * _text_len(node) > root_len or _contains(node, frozenset({"main", "h1"}))


def _drop(node: _Node, full: bool, sectioned: bool, root_len: int, guess: bool = True) -> bool:
    if node.tag in _NON_CONTENT or _is_hidden(node):
        return True
    if full:
        return False
    if node.tag in _CHROME_TAGS:
        return True
    # A page-level header or footer is site chrome; inside an article it holds the title,
    # byline or notes.
    if node.tag in ("header", "footer") and not sectioned:
        return True
    roles = node.attrs.get("role", "").lower().split()
    if roles and roles[0] in _CHROME_ROLES:
        return True
    # Syntax highlighters mark up code with classes such as "token comment" or "hljs-comment".
    if not guess or node.tag in _NEVER_GUESS:
        return False
    return _named_like_chrome(node) and not _holds_content(node, root_len)


def _prune(node: _Node, full: bool, sectioned: bool, root_len: int, in_code: bool = False) -> None:
    kept: list[_Node | str] = []
    for child in node.children:
        if isinstance(child, _Node):
            if _drop(child, full, sectioned, root_len, guess=not in_code):
                continue
            sectioned_child = sectioned or child.tag in _SECTIONING
            code_child = in_code or child.tag in _CODE
            _prune(child, full, sectioned_child, root_len, code_child)
        kept.append(child)
    node.children = kept


def _mark_blocks(node: _Node) -> bool:
    nested = [_mark_blocks(child) for child in _elements(node)]
    node.block = node.tag in _BLOCK or any(nested)
    return node.block


def _is_main(node: _Node) -> bool:
    return node.tag == "main" or node.attrs.get("role", "").lower().split()[:1] == ["main"]


def _content_roots(doc: _Node) -> list[list[_Node]]:
    """Return candidate sets of content elements, best first, ending with the whole page.

    The text lengths used to choose include chrome, so a candidate can come out empty once
    pruned (a <main> holding only a menu); the caller then moves on to the next one.
    """
    page_len = _text_len(doc)
    mains: list[_Node] = []
    articles: list[_Node] = []

    def walk(node: _Node, in_article: bool) -> None:
        for child in _elements(node):
            # Do not look for content inside chrome, e.g. <article> elements in a comment list.
            if _drop(child, full=False, sectioned=True, root_len=page_len):
                continue
            if _is_main(child):
                mains.append(child)
            if child.tag == "article" and not in_article:
                articles.append(child)
            walk(child, in_article or child.tag == "article")

    walk(doc, in_article=False)
    candidates = []
    best_main = max(mains, key=_text_len, default=None)
    if best_main is not None and _text_len(best_main):
        candidates.append([best_main])
    if articles := [article for article in articles if _text_len(article)]:
        candidates.append(articles)
    candidates.append([doc])
    return candidates


def _raw_text(node: _Node) -> str:
    return "".join(
        child if isinstance(child, str) else "\n" if child.tag == "br" else _raw_text(child)
        for child in node.children
    )


def _find(node: _Node, predicate) -> _Node | None:
    for child in _elements(node):
        if child.tag in ("svg", "math"):
            continue
        if predicate(child):
            return child
        found = _find(child, predicate)
        if found is not None:
            return found
    return None


def _oneline(text: str) -> str:
    return " ".join(text.split())


def _page_title(doc: _Node) -> str | None:
    title = _find(doc, lambda n: n.tag == "title")
    if title is not None and (text := _oneline(_raw_text(title))):
        return text
    meta = _find(
        doc,
        lambda n: (
            n.tag == "meta"
            and (n.attrs.get("property") or n.attrs.get("name", "")).lower()
            in ("og:title", "twitter:title")
        ),
    )
    if meta is not None and (text := _oneline(meta.attrs.get("content", ""))):
        return text
    h1 = _find(doc, lambda n: n.tag == "h1" and not _is_hidden(n))
    if h1 is not None and (text := _oneline(_raw_text(h1))):
        return text
    return None


def _has_scheme(url: str) -> bool:
    return re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", url) is not None


def _effective_base(doc: _Node, base_url: str | None) -> str | None:
    base = _find(doc, lambda n: n.tag == "base" and "href" in n.attrs)
    if base is None:
        return base_url
    joined = urljoin(base_url or "", base.attrs["href"].strip())
    # A relative <base> with nothing to resolve it against would make every link wrong.
    return joined if _has_scheme(joined) else base_url


# Never escaped by _escape, so their count in the raw text matches the rendered text.
_OPENING_PUNCT = "({\"'\u201c\u2018\u00ab"
_CLOSING_PUNCT = ".,:;!?)}\"'\u201d\u2019\u00bb"
_ESCAPE = re.compile(r"[\\`*\[\]~]|<(?=[A-Za-z/!?])|&(?=#?\w+;)")
# "_" only starts emphasis next to a non-alphanumeric character; snake_case needs no escape.
_UNDERSCORE = re.compile(r"(?<![^\W_])_|_(?![^\W_])")


def _escape(text: str) -> str:
    text = _ESCAPE.sub(lambda m: "&amp;" if m[0] == "&" else "\\" + m[0], text)
    return _UNDERSCORE.sub(r"\\_", text)


def _escape_line_start(line: str) -> str:
    """Stop a line of text from being read as a list item, heading, quote or rule."""
    if match := re.match(r"\d{1,9}([.)])(?=\s|$)", line):
        return f"{line[: match.start(1)]}\\{line[match.start(1) :]}"
    if re.match(r"[-+*](?=\s|$)", line) or line[0] in "#>" or re.fullmatch(r"=+|-+", line):
        return "\\" + line
    return line


def _split_space(text: str) -> tuple[str, str, str]:
    core = text.strip()
    if not core:
        return text, "", ""
    start = text.index(core)
    return text[:start], core, text[start + len(core) :]


def _longest_run(text: str, char: str) -> int:
    return max((len(run) for run in re.findall(f"{re.escape(char)}+", text)), default=0)


def _code_span(text: str) -> str:
    text = _oneline(text)
    if not text:
        return ""
    fence = "`" * (_longest_run(text, "`") + 1)
    pad = " " if text[0] == "`" or text[-1] == "`" else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _format_url(url: str) -> str:
    url = url.replace(" ", "%20").replace("<", "%3C").replace(">", "%3E")
    depth = 0
    for char in url:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth < 0:
            break
    # Balanced parentheses are allowed in a link destination, e.g. Wikipedia's
    # /wiki/Python_(programming_language); unbalanced ones must be escaped.
    if depth != 0:
        url = url.replace("(", "\\(").replace(")", "\\)")
    return url


class _Renderer:
    def __init__(self, base_url: str | None, links: bool, images: bool) -> None:
        self.base_url = base_url
        self.links = links
        self.images = images
        self._in_link = False
        self._marks: set[str] = set()

    def render(self, node: _Node) -> str:
        return "\n\n".join(text for _, text in self._blocks(node))

    # Blocks -----------------------------------------------------------------------------

    def _blocks(self, node: _Node) -> list[tuple[str, str]]:
        blocks: list[tuple[str, str]] = []
        inline: list[str] = []

        def flush() -> None:
            if paragraph := self._paragraph("".join(inline)):
                blocks.append(("p", paragraph))
            inline.clear()

        for child in node.children:
            if isinstance(child, str):
                inline.append(self._text(child))
            elif not child.block:
                inline.append(self._inline_node(child))
            else:
                flush()
                blocks.extend(self._block_node(child, blocks[-1][0] if blocks else None))
        flush()
        return blocks

    def _block_node(self, node: _Node, previous: str | None) -> list[tuple[str, str]]:
        tag = node.tag
        if tag in _HEADINGS:
            text = _oneline(self._inline(node))
            if text.endswith("#"):
                text = text[:-1] + "\\#"
            return [("h", f"{'#' * _HEADINGS[tag]} {text}")] if text else []
        if tag in ("ul", "ol", "menu"):
            kind = "ol" if tag == "ol" else "ul"
            # Two lists in a row with the same marker would merge into one list.
            return self._list(node, ordered=kind == "ol", alt=previous == kind)
        if tag == "pre":
            return self._pre(node)
        if tag == "blockquote":
            return self._quote(node)
        if tag == "hr":
            return [("hr", "---")]
        if tag == "table":
            return self._table(node)
        if tag == "dt":
            text = _oneline(self._inline(node))
            return [("p", f"**{text}**")] if text else []
        return self._blocks(node)

    def _paragraph(self, inline: str) -> str:
        lines = (re.sub(r" {2,}", " ", line).strip() for line in inline.split("\n"))
        # A trailing backslash is a hard line break, which is what <br> means.
        return "\\\n".join(_escape_line_start(line) for line in lines if line)

    def _list(self, node: _Node, ordered: bool, alt: bool = False) -> list[tuple[str, str]]:
        items: list[list[tuple[str, str]]] = []
        for child in node.children:
            if isinstance(child, str):
                text = self._paragraph(self._text(child))
                blocks = [("p", text)] if text else []
            elif child.tag in ("ul", "ol"):
                previous = items[-1][-1][0] if items else None
                kind = child.tag
                blocks = self._list(child, ordered=kind == "ol", alt=previous == kind)
                # <ul><li>a</li><ul>...</ul></ul> is invalid but common: the nested list
                # belongs to the previous item.
                if items:
                    items[-1].extend(blocks)
                    continue
            elif child.tag == "li" or child.block:
                blocks = self._blocks(child)
            else:
                text = self._paragraph(self._inline_node(child))
                blocks = [("p", text)] if text else []
            if blocks:
                items.append(blocks)
        if not items:
            return []

        number = _list_start(node) if ordered else 1
        loose = any(sum(not _is_list(kind) for kind, _ in blocks) > 1 for blocks in items)
        rendered = []
        for blocks in items:
            marker = f"{number}{')' if alt else '.'}" if ordered else "*" if alt else "-"
            number += 1
            body = blocks[0][1]
            for (prev_kind, _), (kind, text) in zip(blocks, blocks[1:], strict=False):
                body += ("\n" if _is_list(kind) and prev_kind == "p" else "\n\n") + text
            indent = " " * (len(marker) + 1)
            rendered.append(f"{marker} " + re.sub(r"\n(?=[^\n])", "\n" + indent, body))
        kind = "ol" if ordered else "ul"
        # An alternate-marker list is a different kind, so a third list goes back to the default.
        return [(kind + "-alt" if alt else kind, ("\n\n" if loose else "\n").join(rendered))]

    def _pre(self, node: _Node) -> list[tuple[str, str]]:
        text = _raw_text(node)
        # HTML drops the newline right after <pre>.
        text = text.removeprefix("\n").rstrip()
        if not text.strip():
            return []
        fence = "`" * max(3, _longest_run(text, "`") + 1)
        return [("code", f"{fence}{_code_language(node)}\n{text}\n{fence}")]

    def _quote(self, node: _Node) -> list[tuple[str, str]]:
        text = self.render(node)
        if not text:
            return []
        return [("quote", "\n".join(f"> {line}" if line else ">" for line in text.split("\n")))]

    def _table(self, node: _Node) -> list[tuple[str, str]]:
        if _contains(node, frozenset({"table"})):
            # Nested tables are page layout, not data.
            return self._blocks(node)
        grid = []
        for row in _table_rows(node):
            cells: list[str] = []
            for cell in _elements(row):
                if cell.tag in ("td", "th"):
                    cells.append(self._cell(cell))
                    cells.extend([""] * (_colspan(cell) - 1))
            if cells:
                grid.append(cells)
        width = max((len(row) for row in grid), default=0)
        if width < 2:
            # A one-column table is layout too; render its cells as blocks.
            return self._blocks(node)
        if not any(any(row) for row in grid):
            return []
        lines = ["| " + " | ".join(row + [""] * (width - len(row))) + " |" for row in grid]
        lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
        blocks = []
        caption = next((c for c in _elements(node) if c.tag == "caption"), None)
        if caption is not None and (text := self._paragraph(self._inline(caption))):
            blocks.append(("p", text))
        blocks.append(("table", "\n".join(lines)))
        return blocks

    def _cell(self, cell: _Node) -> str:
        return _oneline(self._inline(cell)).replace("|", "\\|")

    # Inline -----------------------------------------------------------------------------

    def _text(self, text: str) -> str:
        return _escape(re.sub(r"\s+", " ", text))

    def _inline(self, node: _Node) -> str:
        return "".join(
            self._text(child) if isinstance(child, str) else self._inline_node(child)
            for child in node.children
        )

    def _inline_node(self, node: _Node) -> str:
        tag = node.tag
        if tag == "br":
            return "\n"
        if tag == "img":
            return self._image(node)
        if tag in ("strong", "b"):
            return self._wrap(node, "**")
        if tag in ("em", "i"):
            return self._wrap(node, "*")
        if tag in ("del", "s", "strike"):
            return self._wrap(node, "~~")
        if tag in ("code", "kbd", "samp", "tt"):
            return _code_span(_raw_text(node))
        if tag == "a":
            return self._link(node)
        if node.block:
            # A block inside inline-only content (a heading, a table cell, link text).
            return f" {self._inline(node)} "
        return self._inline(node)

    def _wrap(self, node: _Node, mark: str) -> str:
        if mark in self._marks:
            return self._inline(node)
        self._marks.add(mark)
        try:
            lead, core, trail = _split_space(self._inline(node))
        finally:
            self._marks.discard(mark)
        if not core:
            return lead
        # CommonMark only closes "**Note:**" before a space or punctuation, so "**Note:**Text"
        # would print the asterisks. Punctuation at the edges of the text is moved outside the
        # markers; link and image markup such as "[a](/b)" at an edge is never split.
        head = _edge_text(node, last=False)
        tail = _edge_text(node, last=True)
        start = len(head) - len(head.lstrip(_OPENING_PUNCT))
        end = len(core) - (len(tail) - len(tail.rstrip(_CLOSING_PUNCT)))
        if start >= end:
            return f"{lead}{mark}{core}{mark}{trail}"
        return f"{lead}{core[:start]}{mark}{core[start:end]}{mark}{core[end:]}{trail}"

    def _link(self, node: _Node) -> str:
        if self._in_link or not self.links:
            return self._inline(node)
        href = self._url(node.attrs.get("href"))
        self._in_link = True
        try:
            text = self._inline(node)
        finally:
            self._in_link = False
        if href is None:
            return text
        lead, core, trail = _split_space(text)
        core = re.sub(r"\s*\n\s*", " ", core)
        if not core:
            return lead
        if _oneline(_raw_text(node)) == href and _has_scheme(href) and " " not in href:
            return f"{lead}<{href}>{trail}"
        return f"{lead}[{core}]({_format_url(href)}){trail}"

    def _image(self, node: _Node) -> str:
        if not self.images:
            return ""
        attrs = node.attrs
        candidates = [
            attrs.get("src", ""),
            attrs.get("data-src", ""),
            attrs.get("data-original", ""),
            attrs.get("data-lazy-src", ""),
            _first_srcset_url(attrs.get("srcset", "")),
            _first_srcset_url(attrs.get("data-srcset", "")),
        ]
        # Lazy-loading pages put a placeholder data: URI in src and the image elsewhere.
        url = next((u for c in candidates if (u := self._url(c)) is not None), None)
        if url is None:
            return ""
        alt = _escape(_oneline(attrs.get("alt", "")))
        return f"![{alt}]({_format_url(url)})"

    def _url(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        url = re.sub(r"[\t\n\r]", "", raw).strip()
        if not url:
            return None
        if _has_scheme(url) and url.split(":", 1)[0].lower() in ("javascript", "vbscript", "data"):
            return None
        return urljoin(self.base_url, url) if self.base_url else url


def _edge_text(node: _Node, last: bool) -> str:
    """Return the visible text at the start (or end) of ``node``; "" if markup comes first."""
    children = reversed(node.children) if last else iter(node.children)
    for child in children:
        if isinstance(child, str):
            if child.strip():
                return child.strip()
        elif child.tag in ("a", "img", "code", "kbd", "samp", "tt"):
            return ""
        elif child.tag != "br":
            return _edge_text(child, last)
    return ""


def _is_list(kind: str) -> bool:
    return kind.startswith(("ul", "ol"))


def _list_start(node: _Node) -> int:
    try:
        return min(max(int(node.attrs.get("start", "1")), 0), 999_999_999)
    except ValueError:
        return 1


def _colspan(cell: _Node) -> int:
    try:
        return min(max(int(cell.attrs.get("colspan", "1")), 1), 100)
    except ValueError:
        return 1


def _table_rows(table: _Node):
    for child in _elements(table):
        if child.tag == "tr":
            yield child
        elif child.tag in ("thead", "tbody", "tfoot"):
            yield from (row for row in _elements(child) if row.tag == "tr")


def _code_language(pre: _Node) -> str:
    classes = [pre.attrs.get("class", "")]
    classes += [c.attrs.get("class", "") for c in _elements(pre) if c.tag == "code"]
    for value in classes:
        if match := re.search(r"(?:^|\s)(?:language|lang)-([A-Za-z0-9_+#.-]+)", value):
            return match[1]
    return ""


def _first_srcset_url(srcset: str) -> str:
    first = srcset.split(",", 1)[0].split()
    return first[0] if first else ""


def convert(
    html: str,
    *,
    base_url: str | None = None,
    full: bool = False,
    links: bool = True,
    images: bool = True,
) -> Page:
    """Convert an HTML document to Markdown.

    Args:
        html: The document as text. Use :func:`html2md_clean.decode_html` for raw bytes.
        base_url: The page's address, used to make relative links and images absolute.
            A ``<base href>`` in the document is applied on top of it.
        full: Convert the whole page instead of only its main content, keeping navigation,
            headers, footers and other page chrome.
        links: Render links as Markdown links. When false, only their text is kept.
        images: Render images. When false, they are left out.
    """
    if not isinstance(html, str):
        raise TypeError(f"html must be str, not {type(html).__name__}; use decode_html() first")
    builder = _TreeBuilder()
    builder.feed(html.replace("\r\n", "\n").replace("\r", "\n"))
    builder.close()
    doc = builder.root

    title = _page_title(doc)
    renderer = _Renderer(_effective_base(doc, base_url), links=links, images=images)
    parts: list[str] = []
    for roots in [[doc]] if full else _content_roots(doc):
        for root in roots:
            sectioned = root.tag in _SECTIONING or _is_main(root)
            _prune(root, full, sectioned, _text_len(root))
            _mark_blocks(root)
            if markdown := renderer.render(root):
                parts.append(markdown)
        if parts:
            break
    return Page(title=title, markdown="\n\n".join(parts))


def html_to_markdown(html: str, **options) -> str:
    """Convert an HTML document to Markdown; see :func:`convert` for the options."""
    return convert(html, **options).markdown
