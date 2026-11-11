import pytest

from html2md_clean import decode_html


def test_defaults_to_utf8_and_replaces_bad_bytes():
    assert decode_html("<p>café</p>".encode()) == "<p>café</p>"
    assert decode_html(b"<p>\xff</p>") == "<p>�</p>"


@pytest.mark.parametrize(
    ("bom", "encoding"),
    [(b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")],
)
def test_bom_wins_over_declarations(bom, encoding):
    data = bom + '<meta charset="latin-1"><p>ç</p>'.encode(encoding)
    assert decode_html(data, "text/html; charset=shift_jis") == '<meta charset="latin-1"><p>ç</p>'


def test_header_charset_wins_over_meta():
    data = '<meta charset="utf-8"><p>é</p>'.encode("latin-1")
    assert decode_html(data, 'text/html; charset="ISO-8859-1"').endswith("<p>é</p>")


def test_meta_charset_and_http_equiv():
    assert decode_html("<meta charset=windows-1251><p>Привет</p>".encode("cp1251")).endswith(
        "Привет</p>"
    )
    data = '<meta http-equiv="Content-Type" content="text/html; charset=shift_jis"><p>日本</p>'
    assert decode_html(data.encode("shift_jis")).endswith("<p>日本</p>")


def test_latin1_labels_mean_windows_1252():
    # 0x93/0x94 are curly quotes in windows-1252 but control characters in ISO-8859-1.
    assert decode_html(b"\x93hi\x94", "text/html; charset=iso-8859-1") == "“hi”"


def test_meta_declaring_utf16_is_read_as_utf8():
    assert decode_html('<meta charset="utf-16"><p>é</p>'.encode()).endswith("<p>é</p>")


@pytest.mark.parametrize("label", ["nonsense", "base64", "rot13", ""])
def test_unknown_or_non_text_codecs_fall_back_to_utf8(label):
    data = f'<meta charset="{label}"><p>é</p>'.encode()
    assert decode_html(data, f"text/html; charset={label}").endswith("<p>é</p>")


def test_meta_after_first_4k_is_ignored():
    data = b" " * 4096 + '<meta charset="cp1251"><p>é</p>'.encode()
    assert decode_html(data).endswith("<p>é</p>")


@pytest.mark.parametrize("label", ["ISO_8859-1", "cp819", "iso-ir-100", "latin_1", "US-ASCII"])
def test_every_latin1_alias_means_windows_1252(label):
    assert decode_html(b"\x93hi\x94", f"text/html; charset={label}") == "“hi”"


def test_xml_declaration_names_the_encoding():
    data = '<?xml version="1.0" encoding="ISO-8859-1"?>\n<p>é</p>'.encode("latin-1")
    assert decode_html(data).endswith("<p>é</p>")
    # The HTTP header still wins.
    data = "<?xml encoding='latin-1'?><p>é</p>".encode()
    assert decode_html(data, "text/html; charset=utf-8").endswith("<p>é</p>")
