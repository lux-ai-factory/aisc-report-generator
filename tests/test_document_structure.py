"""Document structure.

Settings per layout in snapshot `document` (toc on/off, numbering), the chapter and appendix
block types, nesting in the TOC, numbering, and TOC page numbers in the PDF only.
"""
import re

import pytest

from conftest import soup, text
from v2_core_helpers import H, blk, do_render, pdf_pages, service, snap

pytestmark = pytest.mark.db


def ft(title, **o):
    return blk("free_text", title=title, text=f"Body of {title}.", **o)


def heading_text(html, instance_id):
    node = soup(html).find(id=f"block-{instance_id}")
    assert node is not None, f"no element block-{instance_id}"
    h = node.find(["h1", "h2"])
    assert h is not None
    return text(h)


def toc(html):
    return soup(html).find(id="toc")


# toc on / off.

def test_toc_on_shows_it_for_two_blocks(deps):
    html = do_render(deps, snap([ft("a"), ft("b")], document={"toc": "on"}))["html"]
    assert toc(html) is not None


def test_toc_off_never_shows_it(deps):
    html = do_render(deps, snap([ft(x) for x in "abcde"], document={"toc": "off"}))["html"]
    assert toc(html) is None


def test_toc_on_is_placed_after_the_cover(deps):
    cover, a = blk("cover"), ft("a")
    html = do_render(deps, snap([cover, a], document={"toc": "on"}))["html"]
    assert html.index(f'id="block-{cover["instance_id"]}"') < html.index('id="toc"') < html.index(
        f'id="block-{a["instance_id"]}"')


# Chapter and appendix.

def test_chapter_and_appendix_are_built_in(registry):
    chapter, appendix = registry.block("chapter"), registry.block("appendix")
    assert chapter is not None, "missing feature: block type chapter"
    assert appendix is not None, "missing feature: block type appendix"
    assert chapter.reads == () and appendix.reads == ()
    schema = chapter.full_options_schema()
    assert "title" in schema.get("required", [])
    assert schema["properties"]["intro"]["maxLength"] == 5000
    assert chapter.full_default_options()["page_break_before"] is True
    assert chapter.full_default_options()["title"] == "Chapter"
    chapter.validate_declaration()
    appendix.validate_declaration()


def test_a_chapter_renders_its_heading_and_intro(deps):
    ch = blk("chapter", title="System and risks", intro="Read **this** first.", page_break_before=True)
    result = do_render(deps, snap([ch, ft("a")]))
    node = soup(result["html"]).find("section", id=f"block-{ch['instance_id']}")
    assert node is not None and "chapter" in node.get("class", [])
    h1 = node.find("h1", class_="chapter-title")
    assert h1 is not None and text(h1) == "System and risks"
    assert node.find("strong") is not None and "this" in text(node.find("strong"))
    status = [s for s in result["block_statuses"] if s["instance_id"] == ch["instance_id"]][0]
    assert status["status"] == "ok"


def test_the_appendix_heading_and_its_title_override(deps):
    ap, ap2 = blk("appendix"), blk("appendix", title="Annexes")
    one = do_render(deps, snap([ft("a"), ap]))["html"]
    assert heading_text(one, ap["instance_id"]) == "Appendix"
    two = do_render(deps, snap([ft("a"), ap2]))["html"]
    assert heading_text(two, ap2["instance_id"]) == "Annexes"


def test_the_appendix_starts_a_new_page(deps):
    ap = blk("appendix", page_break_before=False)
    html = do_render(deps, snap([ft("a"), ap]))["html"]
    node = soup(html).find(id=f"block-{ap['instance_id']}")
    assert node is not None and "break-before: page" in (node.get("style") or "")


def test_two_appendices_are_refused(deps):
    r = service(deps).post("/v1/render", headers=H, json=snap([ft("a"), blk("appendix"), blk("appendix")]))
    assert r.status_code == 422
    body = r.json()
    problems = body.get("problems") or body.get("error", {}).get("details") or []
    assert any(p.get("code") == "duplicate_appendix" for p in problems), body


# TOC entries and nesting.

def test_toc_lists_chapters_with_their_blocks_nested(deps):
    cover, a, ch, b, c, ap, e = (blk("cover"), ft("a"), blk("chapter", title="X"), ft("b"), ft("c"),
                                 blk("appendix"), ft("e"))
    html = do_render(deps, snap([cover, a, ch, b, c, ap, e], document={"toc": "on"}))["html"]
    nav = toc(html)
    assert nav is not None
    hrefs = [x["href"] for x in nav.find_all("a")]
    assert f"#block-{cover['instance_id']}" not in hrefs
    for x in (a, ch, b, c, ap, e):
        assert f"#block-{x['instance_id']}" in hrefs
    chapter_li = nav.find("a", href=f"#block-{ch['instance_id']}").find_parent("li")
    nested = chapter_li.find("ol")
    assert nested is not None, "the blocks of a chapter are nested under it"
    assert {y["href"] for y in nested.find_all("a")} == {f"#block-{b['instance_id']}", f"#block-{c['instance_id']}"}


# Numbering.

def test_simple_numbering(deps):
    cover, a, b = blk("cover"), ft("a"), ft("b")
    html = do_render(deps, snap([cover, a, b], document={"numbering": True}))["html"]
    assert heading_text(html, a["instance_id"]) == "1 a"
    assert heading_text(html, b["instance_id"]) == "2 b"


def test_numbering_with_chapters_and_appendix(deps):
    """[cover, a, chapter X, b, c, chapter Y, d, appendix, e, chapter Z, f]."""
    cover, a = blk("cover"), ft("a")
    X, b, c = blk("chapter", title="X"), ft("b"), ft("c")
    Y, d = blk("chapter", title="Y"), ft("d")
    ap, e = blk("appendix"), ft("e")
    Z, f = blk("chapter", title="Z"), ft("f")
    layout = [cover, a, X, b, c, Y, d, ap, e, Z, f]
    html = do_render(deps, snap(layout, document={"numbering": True, "toc": "on"}))["html"]
    expected = [(a, "1 a"), (X, "2 X"), (b, "2.1 b"), (c, "2.2 c"), (Y, "3 Y"), (d, "3.1 d"), (e, "A e"),
                (Z, "B Z"), (f, "B.1 f")]
    got = [heading_text(html, k["instance_id"]) for k, _ in expected]
    assert got == [v for _, v in expected]
    assert heading_text(html, ap["instance_id"]) == "Appendix"            # never numbered
    nav = toc(html)
    assert text(nav.find("a", href=f"#block-{b['instance_id']}")).startswith("2.1 b")
    assert text(nav.find("a", href=f"#block-{f['instance_id']}")).startswith("B.1 f")


def test_no_numbering_by_default(deps):
    """Compatibility pin: without numbering the heading is the title alone."""
    a = ft("a")
    html = do_render(deps, snap([blk("cover"), a]))["html"]
    assert heading_text(html, a["instance_id"]) == "a"


# TOC heading and page numbers.

def test_the_toc_heading_is_contents(deps):
    html = do_render(deps, snap([ft(x) for x in "abcd"]))["html"]
    assert text(toc(html).find("h2")) == "Contents"


def test_the_preview_toc_has_no_page_numbers(deps):
    """Compatibility pin: TOC page numbers are in the PDF only."""
    html = do_render(deps, snap([ft(x) for x in "abcd"]))["html"]
    assert "target-counter" not in str(toc(html))
    assert not re.search(r"\d", text(toc(html)).replace("Contents", ""))


def test_pdf_toc_entries_end_with_the_page_number(deps):
    cover = blk("cover", report_title="Paged report")
    alpha, bravo, charlie = (ft("Alphasection", page_break_before=True), ft("Bravosection", page_break_before=True),
                             ft("Charliesection", page_break_before=True))
    pages = pdf_pages(do_render(deps, snap([cover, alpha, bravo, charlie], mode="pdf")))
    toc_page = next(i for i, p in enumerate(pages) if "Contents" in p)
    body_page = next(i for i, p in enumerate(pages) if i != toc_page and "Body of Bravosection." in p)
    assert body_page + 1 >= 3
    line = next(ln for ln in pages[toc_page].splitlines() if "Bravosection" in ln)
    assert re.search(rf"{body_page + 1}\s*$", line), f"TOC line {line!r} does not end with page {body_page + 1}"


# Commentary under chapter and appendix headings.

@pytest.mark.parametrize("block_type,options", [("chapter", {"title": "X"}), ("appendix", {})])
def test_chapter_and_appendix_accept_commentary(deps, block_type, options):
    b = blk(block_type, commentary="Why this part matters", **options)
    html = do_render(deps, snap([ft("a"), b]))["html"]
    node = soup(html).find(id=f"block-{b['instance_id']}")
    assert node is not None
    com = node.find(class_="commentary")
    assert com is not None and "Why this part matters" in text(com)


# One number per TOC entry when numbering is on.

def _numbered_layout():
    cover, a = blk("cover", report_title="Numbered report"), ft("Alphasection")
    X, b = blk("chapter", title="Xchapter"), ft("Bravosection")
    ap, e = blk("appendix"), ft("Echosection")
    return [cover, a, X, b, ap, e]


def _pdf_html_and_markers(deps, monkeypatch, s):
    """Render in pdf mode, keep the HTML handed to WeasyPrint, and list the list-marker texts WeasyPrint
    lays out for it (pypdf does not extract markers, so the PDF text alone cannot show them)."""
    import report_renderer.document as document
    from weasyprint import HTML

    seen = {}
    real = document.html_to_pdf

    def capture(html):
        seen["html"] = html
        return real(html)

    monkeypatch.setattr(document, "html_to_pdf", capture)
    do_render(deps, s)

    def walk(box):
        yield box
        for child in getattr(box, "children", None) or []:
            yield from walk(child)

    markers = []
    for page in HTML(string=seen["html"]).render().pages:
        for box in walk(page._page_box):
            if type(box).__name__ == "TextBox" and (getattr(box, "element_tag", "") or "").endswith("::marker"):
                markers.append(box.text.strip())
    return seen["html"], markers


def test_pdf_toc_shows_each_number_once(deps, monkeypatch):
    """The number precedes the TOC entry once; no list marker in front of it, none on the appendix."""
    s = snap(_numbered_layout(), mode="pdf", document={"numbering": True, "toc": "on"})
    html, markers = _pdf_html_and_markers(deps, monkeypatch, s)
    assert markers == [], f"list markers drawn in front of numbered TOC entries: {markers}"
    nav = toc(html)
    assert [text(a) for a in nav.find_all("a")] == ["1 Alphasection", "2 Xchapter", "2.1 Bravosection",
                                                     "Appendix", "A Echosection"]


def test_without_numbering_the_toc_keeps_its_list_markers(deps, monkeypatch):
    """Compatibility: numbering off keeps the decimal list markers (the goldens rely on it)."""
    s = snap(_numbered_layout(), mode="pdf", document={"toc": "on"})
    _, markers = _pdf_html_and_markers(deps, monkeypatch, s)
    assert markers[:3] == ["1.", "2.", "1."], markers


def test_docx_toc_shows_each_number_once(deps):
    from v2_core_helpers import docx_of

    s = snap(_numbered_layout(), mode="docx", document={"numbering": True, "toc": "on"})
    doc = docx_of(do_render(deps, s))
    texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    start = texts.index("Contents")
    toc_texts = texts[start + 1:start + 6]
    assert toc_texts == ["1 Alphasection", "2 Xchapter", "2.1 Bravosection", "Appendix", "A Echosection"], toc_texts
    for p in doc.paragraphs[:40]:
        assert p._p.pPr is None or p._p.pPr.numPr is None or not p.text.strip().startswith(("1 ", "2 ", "A ")), p.text
