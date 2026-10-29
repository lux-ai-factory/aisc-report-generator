"""Header, footer, marking, document id and fingerprint.

The template's look in snapshot `style` may carry header_text, footer_text, marking and
show_document_id. They are placed in the page margins (@page boxes); the fingerprint is the SHA-256
of the canonical snapshot without mode, requested_by and document.
"""
import copy
import hashlib
import json
import re

import pytest

from conftest import need, soup, text
from v2_core_helpers import blk, do_render, pdf_pages, snap

pytestmark = pytest.mark.db
DOC_ID = "3c9d1f2e-7a6b-4c5d-8e9f-0a1b2c3d4e5f"


def look(**over):
    s = {"font": "inter", "font_size_pt": 10, "primary_color": "#000fdf", "accent_color": "#ff007e"}
    s.update(over)
    return s


def css_of(html):
    return soup(html).find("style").string


# Placement and defaults.

def test_defaults_keep_todays_header_and_footer(deps):
    """Compatibility pin: without header_text, footer_text or marking, the two default margin boxes."""
    css = css_of(do_render(deps, snap([blk("free_text", text="x")], style=look()))["html"])
    assert '@top-left { content: "Alpha project, Version 2"' in css
    assert '@bottom-right { content: "Page " counter(page) " of " counter(pages)' in css
    for box in ("@top-right", "@bottom-left", "@bottom-center"):
        assert box not in css


def test_header_footer_and_marking_are_placed_in_the_margins(deps):
    st = look(header_text="Example Assistant assessment", footer_text="For internal review", marking="confidential")
    css = css_of(do_render(deps, snap([blk("free_text", text="x")], style=st))["html"])
    assert re.search(r'@top-left\s*\{\s*content:\s*"Example Assistant assessment"', css)
    assert re.search(r'@top-right\s*\{\s*content:\s*"CONFIDENTIAL"', css)
    assert re.search(r'@bottom-left\s*\{\s*content:\s*"For internal review"', css)
    top_right = css[css.index("@top-right"):].split("}")[0]
    assert "#ff007e" in top_right.lower(), "the marking is printed in the accent colour"


def test_the_pdf_shows_them_on_every_page(deps):
    st = look(header_text="Example Assistant assessment", footer_text="For internal review", marking="strictly_confidential")
    blocks = [blk("free_text", text="one"), blk("free_text", text="two", page_break_before=True)]
    pages = pdf_pages(do_render(deps, snap(blocks, mode="pdf", style=st)))
    assert len(pages) >= 2
    for p in pages:
        assert "Example Assistant assessment" in p and "For internal review" in p and "STRICTLY CONFIDENTIAL" in p


@pytest.mark.parametrize("marking,label", [("public", "PUBLIC"), ("internal", "INTERNAL"),
                                           ("confidential", "CONFIDENTIAL"),
                                           ("strictly_confidential", "STRICTLY CONFIDENTIAL")])
def test_marking_labels(deps, marking, label):
    css = css_of(do_render(deps, snap([blk("free_text", text="x")], style=look(marking=marking)))["html"])
    assert f'"{label}"' in css


def test_the_marking_is_printed_on_the_cover_under_the_title(deps):
    cover = blk("cover", report_title="Example Assistant report")
    html = do_render(deps, snap([cover], style=look(marking="internal")))["html"]
    node = soup(html).find(id=f"block-{cover['instance_id']}")
    t = text(node)
    assert "Internal" in t and t.index("Example Assistant report") < t.index("Internal")


def test_no_marking_none_on_the_cover(deps):
    cover = blk("cover", report_title="Example Assistant report")
    html = do_render(deps, snap([cover], style=look(marking="none")))["html"]
    assert "Confidential" not in html and "Internal" not in text(soup(html).find(id=f"block-{cover['instance_id']}"))


# Placeholders.

def test_placeholders_are_filled_and_unknown_ones_kept(deps):
    st = look(header_text="{project} v{version} r{release} {layout} {date} {unknown} {",
              footer_text="{project}")
    css = css_of(do_render(deps, snap([blk("free_text", text="x")], style=st))["html"])
    assert '"Alpha project v2 r1.0 Quarterly report 2026-09-20 {unknown} {"' in css
    assert re.search(r'@bottom-left\s*\{\s*content:\s*"Alpha project"', css)


def test_the_text_is_escaped_for_a_css_string(deps):
    st = look(header_text='Say "hi" \\ </style><script>x</script>')
    html = do_render(deps, snap([blk("free_text", text="x")], style=st))["html"]
    assert "<script>x</script>" not in html
    assert '"Say \\"hi\\" \\\\ \\3c /style>\\3c script>x\\3c /script>"' in css_of(html)


# The document id line.

def test_the_document_id_line_in_a_pdf(deps):
    s = snap([blk("free_text", text="x")], mode="pdf", style=look(show_document_id=True),
             document={"id": DOC_ID})
    result = do_render(deps, s)
    assert "fingerprint" in result, "missing feature: the render result carries the fingerprint"
    line = f"Document {DOC_ID[:8]} | Fingerprint {result['fingerprint'][:12]}"
    assert all(line in p for p in pdf_pages(result))


def test_the_preview_says_it_is_not_a_document(deps):
    s = snap([blk("free_text", text="x")], style=look(show_document_id=True), document={"id": None})
    css = css_of(do_render(deps, s)["html"])
    assert re.search(r'@bottom-center\s*\{\s*content:\s*"Preview, not a generated document"', css)


def test_no_id_line_when_off(deps):
    s = snap([blk("free_text", text="x")], style=look(show_document_id=False), document={"id": DOC_ID})
    assert "@bottom-center" not in css_of(do_render(deps, s)["html"])


# The fingerprint.

def expected_fingerprint(s):
    s = copy.deepcopy(s)
    for k in ("mode", "requested_by", "document"):
        s.pop(k, None)
    raw = json.dumps(s, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_the_fingerprint_is_the_sha256_of_the_canonical_snapshot(deps):
    s = snap([blk("free_text", text="Grüße")], style=look(), document={"id": DOC_ID, "toc": "on"})
    result = do_render(deps, s)
    assert result.get("fingerprint") == expected_fingerprint(s)


@pytest.mark.parametrize("mode", ["preview", "pdf"])
def test_every_mode_returns_the_fingerprint(deps, mode):
    s = snap([blk("free_text", text="x")], mode=mode)
    result = do_render(deps, s)
    assert result.get("fingerprint") == expected_fingerprint(s)


def test_mode_requester_and_document_do_not_change_it_content_does(deps):
    b = blk("free_text", text="x")
    one = do_render(deps, snap([b], requested_by="alice", document={"id": DOC_ID}))
    two = do_render(deps, snap([b], mode="pdf", document={"id": None}) | {"requested_by": "bob"})
    b2 = dict(b, options={"text": "y"})
    three = do_render(deps, snap([b2]))
    assert one.get("fingerprint") and one["fingerprint"] == two.get("fingerprint")
    assert three.get("fingerprint") != one["fingerprint"]


# No character can leave the CSS string.

NASTY = [
    ("form feed", "x\f}} p { display: none } @page { @top-left {"),
    ("vertical tab and other controls", "a\v\x00\x01\x1b\x7f\x85b"),
    ("backslash", "C:\\temp\\ \\\" \\"),
    ("quotes", "\"double\" 'single' \"unclosed"),
    ("newlines", "one\ntwo\r\nthree\rfour"),
    ("line and paragraph separators", "a\u2028b\u2029c"),
    ("end of style", "</style><script>alert(1)</script></STYLE >"),
    ("unicode", "Réponses aux contrôles, Ünïcödé 数据 \U0001F512 \u00a0nbsp \u200bzw"),
    ("trailing backslash", "ends with \\"),
]


@pytest.mark.parametrize("name,value", NASTY, ids=[n for n, _ in NASTY])
def test_the_header_css_string_is_one_string_token_with_the_text(name, value):
    """Whatever the text, the CSS is exactly one string token whose value is the text (CR/LF shown as a space),
    and the HTML parser can never see an end tag in it."""
    import tinycss2

    css_string = need("report_renderer.document", "_css_string")
    out = css_string(value)
    tokens = [t for t in tinycss2.parse_component_value_list(out) if t.type != "whitespace"]
    assert len(tokens) == 1 and tokens[0].type == "string", (out, tokens)
    expected = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\x00", "\ufffd")
    assert tokens[0].value == expected
    assert "<" not in out
    assert all(ch.isprintable() for ch in out), repr(out)


def test_a_form_feed_in_the_header_does_not_restyle_the_pdf(deps):
    st = look(header_text="x\f}} p { display: none } @page { @top-left {")
    blocks = [blk("free_text", title="Visible", text="This paragraph must stay visible.")]
    pages = pdf_pages(do_render(deps, snap(blocks, mode="pdf", style=st)))
    body = " ".join(pages).replace("\x00", "")   # pypdf may return this page's text as UTF-16 code units
    assert "This paragraph must stay visible." in body
    assert "\f" not in css_of(do_render(deps, snap(blocks, style=st))["html"])


def test_control_characters_in_the_header_do_not_break_the_word_file(deps):
    from v2_core_helpers import docx_of

    st = look(header_text="Head\fer\x01 text", footer_text="Foot\x0b er")
    doc = docx_of(do_render(deps, snap([blk("free_text", text="x")], mode="docx", style=st)))
    header = " ".join(p.text for p in doc.sections[0].header.paragraphs)
    footer = " ".join(p.text for p in doc.sections[0].footer.paragraphs)
    assert "Head" in header and "er" in header and " text" in header
    assert "Foot" in footer
