import pytest

from html2md_clean import Page, convert, html_to_markdown
from html2md_clean.convert import MAX_DEPTH


def md(html: str, **options) -> str:
    return html_to_markdown(html, **options)


PAGE = """<!doctype html><html><head><title>Release notes | Example</title></head><body>
<header><nav><a href="/">Home</a></nav></header>
<div class="cookie-banner">We use cookies.</div>
<main><article>
  <header><h1>Release 2.0</h1><p>By Ana</p></header>
  <p>Body text.</p>
  <div class="share-buttons"><a href="#">Share</a></div>
  <footer><p>Article notes</p></footer>
</article></main>
<aside>Related posts</aside>
<footer>Copyright</footer>
</body></html>"""


def test_convert_returns_title_and_main_content_only():
    page = convert(PAGE)
    assert page == Page(
        title="Release notes | Example",
        markdown="# Release 2.0\n\nBy Ana\n\nBody text.\n\nArticle notes",
    )


def test_full_keeps_page_chrome():
    text = md(PAGE, full=True)
    for chrome in ("[Home](/)", "We use cookies.", "Share", "Related posts", "Copyright"):
        assert chrome in text
    assert "Release notes" not in text  # <head> is never content


def test_falls_back_to_articles_then_whole_page():
    html = "<body><nav>Menu</nav><article><p>One</p></article><article><p>Two</p></article></body>"
    assert md(html) == "One\n\nTwo"
    assert md("<body><nav>Menu</nav><p>Plain page</p><footer>Foot</footer></body>") == "Plain page"


def test_picks_largest_main_and_ignores_empty_one():
    html = "<main></main><main><p>Real content</p></main><p>outside</p>"
    assert md(html) == "Real content"
    assert md("<main>  </main><p>Only text</p>") == "Only text"


def test_role_main_counts_as_main():
    assert md('<div>Chrome</div><div role="main"><p>Content</p></div>') == "Content"


def test_articles_inside_comment_section_are_not_content():
    html = """<body><article><p>Post body that is long enough to matter here.</p></article>
    <section id="comments"><article><p>Nice post!</p></article></section></body>"""
    assert md(html) == "Post body that is long enough to matter here."


@pytest.mark.parametrize(
    "chrome",
    [
        "<nav>x</nav>",
        "<aside>x</aside>",
        '<div role="navigation">x</div>',
        '<div class="main-nav">x</div>',
        '<div id="cookieConsent">x</div>',
        '<ul class="social share">x</ul>',
        "<p hidden>x</p>",
        '<p aria-hidden="true">x</p>',
        '<p style="display: none">x</p>',
        "<script>x</script>",
        "<style>x</style>",
        "<noscript>x</noscript>",
        "<button>x</button>",
    ],
)
def test_removes_chrome(chrome):
    assert md(f"<body><p>Keep this text</p>{chrome}</body>") == "Keep this text"


def test_class_names_match_whole_words_only():
    # "canvas" contains "nav", "header" contains "ad" and "shared" is not "share".
    html = '<div class="canvas header-shared"><p>Keep</p></div><p>more text</p>'
    assert md(html) == "Keep\n\nmore text"


def test_chrome_named_wrapper_holding_most_content_is_kept():
    html = (
        '<div class="has-sidebar"><p>Article</p></div>'
        '<div class="sidebar-layout"><p>Long article text here</p></div><p>x</p>'
    )
    assert md(html) == "Article\n\nLong article text here\n\nx"


def test_hidden_until_found_is_kept():
    assert md('<p hidden="until-found">Folded</p>') == "Folded"


def test_headers_inside_sections_are_kept():
    html = "<header>Site</header><section><header><h2>Part</h2></header><p>a</p></section>"
    assert md(html) == "## Part\n\na"


def test_headings_and_paragraphs():
    assert md("<h1>T</h1><h3>Sub <em>x</em></h3><p>a\n  b</p>") == "# T\n\n### Sub *x*\n\na b"
    assert md("<h2> </h2><p></p>") == ""
    assert md("<h2>Item #</h2>") == "## Item \\#"


def test_line_breaks_are_hard_breaks():
    assert md("<p>one<br>two<br/><br>three</p>") == "one\\\ntwo\\\nthree"


def test_inline_formatting():
    html = "<p><b>bold</b> <strong> spaced </strong>x <i>it</i> <s>old</s> <b><b>twice</b></b></p>"
    assert md(html) == "**bold** **spaced** x *it* ~~old~~ **twice**"
    assert md("<p>a<b> </b>b<em></em>c</p>") == "a bc"


def test_code_spans():
    assert md("<p>Use <code>a  *b*</code> or <kbd>Ctrl</kbd></p>") == "Use `a *b*` or `Ctrl`"
    assert md("<p><code>a`b</code> <code>`x</code></p>") == "``a`b`` `` `x ``"


def test_escapes_markdown_in_text():
    html = (
        "<p>*stars* [link] `tick` \\ snake_case _under_ __init__ 2 < 3 <b>x</b> "
        "&lt;div&gt; ~~no~~</p>"
    )
    assert md(html) == (
        "\\*stars\\* \\[link\\] \\`tick\\` \\\\ snake_case \\_under\\_ \\_\\_init\\_\\_ "
        "2 < 3 **x** \\<div> \\~\\~no\\~\\~"
    )
    assert md("<p>&amp;copy; &amp; AT&amp;T</p>") == "&amp;copy; & AT&T"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("# not a heading", "\\# not a heading"),
        ("> not a quote", "\\> not a quote"),
        ("- not a list", "\\- not a list"),
        ("+ plus", "\\+ plus"),
        ("1. not ordered", "1\\. not ordered"),
        ("2024) year", "2024\\) year"),
        ("===", "\\==="),
        ("---", "\\---"),
        ("2024 was fine", "2024 was fine"),
        ("#hashtag", "\\#hashtag"),
    ],
)
def test_escapes_block_syntax_at_line_start(text, expected):
    assert md(f"<p>{text}</p>") == expected
    assert md(f"<p>first<br>{text}</p>") == f"first\\\n{expected}"


def test_links():
    html = (
        '<p><a href="/a">rel</a> <a href="https://x.org/">https://x.org/</a> '
        '<a href="javascript:alert(1)">js</a> <a>no href</a> <a href="/empty"> </a> '
        '<a href=" JavaScript:x">js2</a> <a href="/w/Python_(language)">wiki</a> '
        '<a href="/odd)path">odd</a> <a href="/a b">space</a></p>'
    )
    assert md(html) == (
        "[rel](/a) <https://x.org/> js no href "
        "js2 [wiki](/w/Python_(language)) [odd](/odd\\)path) [space](/a%20b)"
    )


def test_links_resolve_against_base_url_and_base_tag():
    html = '<base href="/docs/"><p><a href="intro">i</a> <img src="a.png" alt="A"></p>'
    assert md(html, base_url="https://ex.com/x/page") == (
        "[i](https://ex.com/docs/intro) ![A](https://ex.com/docs/a.png)"
    )
    # A relative <base> with no page address to resolve it against is ignored.
    assert md(html) == "[i](intro) ![A](a.png)"
    assert md('<p><a href="#s">s</a></p>', base_url="https://ex.com/p") == "[s](https://ex.com/p#s)"


def test_nested_links_and_link_options():
    assert md('<p><a href="/a">x <a href="/b">y</a></a></p>') == "[x](/a) [y](/b)"
    assert md('<p>see <a href="/a">this <b>page</b></a>.</p>', links=False) == "see this **page**."


def test_link_text_with_line_break_is_one_line():
    assert md('<p><a href="/a">one<br>two</a></p>') == "[one two](/a)"


def test_images():
    html = (
        '<p><img src="/a.png" alt="A *b*"> '
        '<img src="data:image/gif;base64,AA" data-src="/lazy.png">'
        ' <img srcset="/s1.png 1x, /s2.png 2x"> <img alt="no src"> <img src="data:x"></p>'
    )
    assert md(html) == "![A \\*b\\*](/a.png) ![](/lazy.png) ![](/s1.png)"
    assert md(html, images=False) == ""


def test_linked_image():
    assert md('<a href="/big.png"><img src="/small.png" alt="pic"></a>') == (
        "[![pic](/small.png)](/big.png)"
    )


def test_lists():
    html = "<ul><li>a<li>b <b>c</b><ul><li>nested</li></ul></ul><ol><li>x</li><li>y</li></ol>"
    assert md(html) == "- a\n- b **c**\n  - nested\n\n1. x\n2. y"


def test_loose_list_and_start_attribute():
    html = '<ol start="9"><li><p>one</p><p>more</p></li><li>two</li></ol>'
    assert md(html) == "9. one\n\n   more\n\n10. two"
    assert md('<ol start="x"><li>a</li></ol>') == "1. a"


def test_list_quirks():
    # A nested list placed directly inside <ul> belongs to the previous item.
    assert md("<ul><li>a</li><ul><li>b</li></ul></ul>") == "- a\n  - b"
    assert md("<ul><ul><li>b</li></ul></ul>") == "- - b"
    assert md("<ul><li></li><li> </li></ul>") == ""
    assert md("<ul> stray <span>text</span></ul>") == "- stray\n- text"


def test_code_in_list_item_is_indented():
    assert md("<ul><li>run<pre>a\n\nb</pre></li></ul>") == "- run\n\n  ```\n  a\n\n  b\n  ```"


def test_pre_blocks():
    html = '<pre class="lang-js">\n  if (a) {\n    b();\n  }\n\n</pre>'
    assert md(html) == "```js\n  if (a) {\n    b();\n  }\n```"
    nested = '<pre><code class="hljs language-c++"><span>int</span> x;<br>``` y</code></pre>'
    assert md(nested) == "````c++\nint x;\n``` y\n````"
    assert md("<pre>  \n </pre>") == ""


def test_blockquote():
    html = "<blockquote><p>a</p><blockquote>b</blockquote></blockquote>"
    assert md(html) == "> a\n>\n> > b"
    assert md("<blockquote> </blockquote>") == ""


def test_horizontal_rule_and_definition_list():
    assert md("<p>a</p><hr><p>b</p>") == "a\n\n---\n\nb"
    assert md("<dl><dt>Term<dd>Meaning<dt>Other<dd>More</dl>") == (
        "**Term**\n\nMeaning\n\n**Other**\n\nMore"
    )


def test_tables():
    html = """<table><caption>Scores</caption>
      <thead><tr><th>Name<th>Value | unit</tr></thead>
      <tbody><tr><td>a<td><b>1</b><br>2<tr><td colspan="2">wide<tr><td>short</tbody></table>"""
    assert md(html) == (
        "Scores\n\n"
        "| Name | Value \\| unit |\n| --- | --- |\n| a | **1** 2 |\n| wide |  |\n| short |  |"
    )


def test_layout_tables_render_as_blocks():
    # The outer table is layout; the data table inside it is kept.
    nested = "<table><tr><td><p>Intro</p><table><tr><td>a<td>b</table></td><td>side</td></table>"
    assert md(nested) == "Intro\n\n| a | b |\n| --- | --- |\n\nside"
    assert md("<table><tr><td><p>one</p></td></tr><tr><td>two</td></tr></table>") == "one\n\ntwo"
    assert md("<table><tr><td></td><td> </td></tr></table>") == ""


def test_stray_end_tags_do_not_escape_table_cells():
    html = "<div><table><tr><td>a</div>b</td><td>c</td></tr></table></div>"
    assert md(html) == "| ab | c |\n| --- | --- |"


def test_block_inside_inline_content():
    assert md("<h2><div>A</div><div>B</div></h2>") == "## A B"
    assert md('<a href="/x"><h3>Card</h3><p>Text</p></a>') == "### Card\n\nText"


def test_unknown_and_custom_elements_are_transparent():
    assert md("<my-card><p>a</p><x-y>b</x-y></my-card>") == "a\n\nb"


def test_self_closing_non_void_elements_do_not_swallow_the_page():
    assert md('<p><a name="top"/>Title</p><p>Next</p>') == "Title\n\nNext"


def test_title_fallbacks():
    assert convert("<svg><title>icon</title></svg><h1>Head</h1>").title == "Head"
    meta = '<meta property="og:title" content=" OG  title "><h1>H</h1>'
    assert convert(meta).title == "OG title"
    assert convert("<p>none</p>").title is None
    assert convert("<title> </title><h1 hidden>x</h1>").title is None


def test_whitespace_and_newlines_are_normalised():
    assert md("<p>a\r\nb\rc d</p>") == "a b c d"
    assert md("") == ""
    assert md("just text") == "just text"


def test_deeply_nested_html_does_not_crash():
    depth = MAX_DEPTH * 5
    html = "<div>" * depth + "<p>deep</p>" + "</div>" * depth + "<p>after</p>"
    assert md(html) == "deep\n\nafter"


def test_rejects_bytes():
    with pytest.raises(TypeError, match="decode_html"):
        convert(b"<p>x</p>")  # type: ignore[arg-type]


def test_highlighted_code_keeps_comments():
    prose = "<p>" + "Some explanation of the example. " * 10 + "</p>"
    html = prose + (
        '<pre><code class="language-py"><span class="token comment"># note</span>\nx = 1\n'
        '<span class="hljs-comment">// other</span></code></pre>'
        '<p>Inline <code><span class="token comment">/* c */</span></code></p>'
    )
    assert md(html).endswith("```py\n# note\nx = 1\n// other\n```\n\nInline `/* c */`")


def test_main_holding_only_chrome_falls_back_to_articles():
    html = "<main><nav>Home Blog About Contact</nav></main><article><p>Post</p></article>"
    assert md(html) == "Post"
    assert md("<main><aside>Accept cookies</aside></main><p>Text</p>") == "Text"


def test_adjacent_lists_stay_separate():
    html = "<ul><li>a</ul><ul><li>b</ul><ul><li>c</ul><ol><li>1</ol><ol><li>2</ol>"
    assert md(html) == "- a\n\n* b\n\n- c\n\n1. 1\n\n1) 2"
    nested = "<ul><li>x<ul><li>a</ul><ul><li>b</ul></li></ul>"
    assert md(nested) == "- x\n  - a\n\n  * b"


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<b>Note:</b>Text", "**Note**:Text"),
        ("a<em>(b)</em>c", "a(*b*)c"),
        ("<b>“Quote.”</b>", "“**Quote**.”"),
        ("<b>...</b>", "**...**"),
        # Escaped brackets stay whole inside the markers.
        ("<b>[x]</b>", "**\\[x\\]**"),
    ],
)
def test_emphasis_moves_edge_punctuation_outside(html, expected):
    assert md(f"<p>{html}</p>") == expected


def test_unclosed_elements_past_max_depth_do_not_eat_end_tags():
    deep = "<div>" * (MAX_DEPTH + 5)
    html = deep + "<ul><li>a<li>b</ul>" + "</div>" * (MAX_DEPTH + 5) + "<p>after</p>"
    assert md(html).endswith("after")
    assert md(html, full=True).endswith("\n\nafter")
