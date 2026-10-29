"""Rendering a layout snapshot into one document. Database tests on the bed.

Fake block types are registered next to the built-ins to observe what the renderer does.
"""
import base64
import hashlib
import io
import logging
import re

import pytest

from conftest import FIXED_NOW, IDS, block, need, render, section, snapshot, soup, status_of, text

pytestmark = pytest.mark.db


def fake_block(type_id="probe", title="Probe", raise_in=None, html="<p>probe</p>", status="ok", notices=(),
               schema=None, defaults=None, seen=None):
    Base = need("aisc_report_plugin_interface", "BaseBlockRenderer")
    BlockResult = need("aisc_report_plugin_interface", "BlockResult")
    seen = seen if seen is not None else []

    def load(self, ctx, options):
        seen.append(("load", ctx, options))
        if raise_in == "load":
            raise RuntimeError("SECRET-TRACEBACK-TEXT in load")
        return {"n": 1}

    def render_(self, data, options, ctx):
        seen.append(("render", ctx, options))
        if raise_in == "render":
            raise ValueError("SECRET-TRACEBACK-TEXT in render")
        return BlockResult(html=html, status=status, notices=list(notices))

    return type(f"Fake_{type_id}", (Base,), {
        "type_id": type_id, "title": title, "contract_version": 1,
        "options_schema": schema or {"type": "object", "properties": {"n": {"type": "integer", "maximum": 5}}},
        "default_options": defaults if defaults is not None else {"n": 1}, "reads": ("platform",),
        "load": load, "render": render_})


def test_a_block_gets_exactly_its_context(registry, deps):
    seen = []
    registry.register_block(fake_block(seen=seen), origin="tests")
    render(deps, [block("probe", n=2)], mode="preview")
    _, ctx, options = seen[0]
    assert str(ctx.project_id) == IDS["A"]
    assert ctx.project["name"] == "Alpha project" and ctx.project["slug"] == "alpha"
    assert str(ctx.system["pid"]) == IDS["A_V2"] and ctx.system["number"] == 2
    assert list(ctx.newer_versions) == [3]
    assert ctx.generated_at == FIXED_NOW and ctx.generated_at.tzinfo is not None
    assert ctx.mode == "preview"
    assert str(ctx.data.project_id) == IDS["A"] and str(ctx.data.system_id) == IDS["A_V2"]
    assert options == {"title": "", "page_break_before": False, "commentary": "", "commentary_position": "after",
                       "n": 2}


def test_no_newer_versions_for_the_latest(registry, deps):
    seen = []
    registry.register_block(fake_block(seen=seen), origin="tests")
    render(deps, [block("probe")], system="A_V3", mode="pdf")
    assert list(seen[0][1].newer_versions) == [] and seen[0][1].mode == "pdf"


def test_each_block_is_wrapped_in_its_section(registry, deps):
    registry.register_block(fake_block(status="stale", notices=["n1"]), origin="tests")
    b = block("probe")
    html = render(deps, [b])["html"]
    node = section(html, b["instance_id"])
    assert node.get("class") == ["block", "block-probe"]
    assert node.get("data-status") == "stale"
    assert text(node.find("h2")) == "Probe"
    assert node.find("p").get_text() == "probe"


def test_the_instance_title_overrides_the_type_title(registry, deps):
    registry.register_block(fake_block(), origin="tests")
    b = block("probe", title="My own heading")
    node = section(render(deps, [b])["html"], b["instance_id"])
    assert text(node.find("h2")) == "My own heading"


def test_blocks_are_rendered_strictly_in_list_order(registry, deps):
    for t in ("probe_a", "probe_b", "probe_c"):
        registry.register_block(fake_block(type_id=t, title=t.upper()), origin="tests")
    blocks = [block("probe_c"), block("probe_a"), block("probe_b"), block("probe_a", title="again")]
    result = render(deps, blocks)
    ids = [s.get("id") for s in soup(result["html"]).find_all("section", class_="block")]
    assert ids == [f"block-{b['instance_id']}" for b in blocks]


def test_block_statuses_in_order(registry, deps):
    registry.register_block(fake_block(type_id="probe_ok"), origin="tests")
    registry.register_block(fake_block(type_id="probe_empty", status="empty", notices=["No data for version 2."]),
                            origin="tests")
    blocks = [block("probe_empty"), block("probe_ok")]
    statuses = render(deps, blocks)["block_statuses"]
    assert statuses == [
        {"instance_id": blocks[0]["instance_id"], "block_type": "probe_empty", "status": "empty",
         "notices": ["No data for version 2."]},
        {"instance_id": blocks[1]["instance_id"], "block_type": "probe_ok", "status": "ok", "notices": []},
    ]


@pytest.mark.parametrize("where", ["load", "render"])
def test_a_failing_block_becomes_an_error_box(registry, deps, caplog, where):
    caplog.set_level(logging.ERROR)
    registry.register_block(fake_block(type_id="boom", raise_in=where), origin="tests")
    registry.register_block(fake_block(type_id="after"), origin="tests")
    bad, good = block("boom"), block("after")
    result = render(deps, [bad, good])
    node = section(result["html"], bad["instance_id"])
    m = re.search(r"This section could not be rendered \(ref ([0-9a-f]{8})\)\.", text(node))
    assert m, text(node)
    assert node.get("data-status") == "error"
    assert status_of(result, bad["instance_id"])["status"] == "error"
    # the traceback is logged with the ref, never shown
    assert "SECRET-TRACEBACK-TEXT" not in result["html"] and "Traceback" not in result["html"]
    assert m.group(1) in caplog.text and "SECRET-TRACEBACK-TEXT" in caplog.text
    # and the next block still renders
    assert status_of(result, good["instance_id"])["status"] == "ok"


def test_invalid_options_are_an_error_and_nothing_is_read(registry, deps):
    seen = []
    registry.register_block(fake_block(seen=seen), origin="tests")
    b = block("probe", n=99)
    result = render(deps, [b])
    s = status_of(result, b["instance_id"])
    assert s["status"] == "error"
    assert any(re.fullmatch(r"Invalid options: n: .+", n) for n in s["notices"]), s["notices"]
    assert not [e for e in seen if e[0] == "load"]


def test_titles_and_options_are_escaped(registry, deps):
    registry.register_block(fake_block(), origin="tests")
    b = block("probe", title="<script>alert(1)</script>")
    result = render(deps, [b])
    assert "<script>alert(1)</script>" not in result["html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result["html"]


def test_an_unknown_block_type_renders_as_an_error(deps):
    b = block("no_such_block_type")
    result = render(deps, [b, block("free_text", text="still here")])
    assert status_of(result, b["instance_id"])["status"] == "error"
    assert "still here" in result["html"]


def test_a_system_of_another_project_is_refused_before_any_read(registry, deps):
    seen = []
    registry.register_block(fake_block(seen=seen), origin="tests")
    NotFound = need("report_renderer.document", "NotFound")
    with pytest.raises(NotFound):
        need("report_renderer.document", "render")(snapshot([block("probe")], project="A", system="B_V1"), deps)
    assert seen == []


def test_a_table_of_contents_after_the_cover(deps):
    blocks = [block("cover"), block("free_text", text="a", title="First text"),
              block("free_text", text="b", title="Second text"), block("free_text", text="c", title="Third text")]
    doc = soup(render(deps, blocks)["html"])
    toc = doc.find(id="toc")
    assert toc is not None
    assert [t for t in ("First text", "Second text", "Third text") if t in text(toc)] == ["First text", "Second text", "Third text"]
    order = [el.get("id") for el in doc.find_all(id=True) if el.get("id") == "toc" or el.name == "section"]
    assert order[0] == f"block-{blocks[0]['instance_id']}" and order[1] == "toc"


def test_the_table_of_contents_is_on_unless_the_document_turns_it_off(deps):
    """However few blocks: "on" is the composer's default; there is no automatic setting."""
    blocks = [block("cover"), block("free_text", text="a"), block("free_text", text="b")]
    assert soup(render(deps, blocks)["html"]).find(id="toc") is not None


def test_one_document_with_one_stylesheet(deps):
    html = render(deps, [block("free_text", text="a")])["html"]
    doc = soup(html)
    assert len(doc.find_all("html")) == 1 and len(doc.find_all("body")) == 1
    assert doc.find("style") is not None
    assert not doc.find_all("link", rel="stylesheet")  # nothing fetched


def test_the_newer_version_banner_without_a_cover(deps):
    b = block("free_text", text="only text")
    doc = soup(render(deps, [b])["html"])
    banner_text = "This report covers version 2. Version 3 is newer."
    assert banner_text in text(doc)
    first_section = doc.find("section", class_="block")
    assert banner_text not in text(first_section)
    assert text(doc).index(banner_text) < text(doc).index("only text")


def test_no_banner_for_the_latest_version(deps):
    html = render(deps, [block("free_text", text="x")], system="A_V3")["html"]
    assert "is newer" not in html


def test_pdf_mode_returns_a_pdf_and_its_hash(deps):
    result = render(deps, [block("cover"), block("free_text", text="hello pdf")], mode="pdf")
    pdf = base64.b64decode(result["pdf_base64"])
    assert pdf[:5] == b"%PDF-"
    assert result["sha256"] == hashlib.sha256(pdf).hexdigest()
    assert len(result["block_statuses"]) == 2


def _pages(pdf_bytes):
    from pypdf import PdfReader

    return PdfReader(io.BytesIO(pdf_bytes)).pages


def test_page_break_before_starts_a_new_page(deps):
    one = render(deps, [block("free_text", text="a"), block("free_text", text="b")], mode="pdf")
    two = render(deps, [block("free_text", text="a"), block("free_text", text="b", page_break_before=True)], mode="pdf")
    n1 = len(_pages(base64.b64decode(one["pdf_base64"])))
    n2 = len(_pages(base64.b64decode(two["pdf_base64"])))
    assert n2 == n1 + 1


# running header/footer with project, version and page numbers in the PDF
def test_every_pdf_page_names_the_project_and_version(deps):
    blocks = [block("free_text", text="x", page_break_before=True) for _ in range(3)]
    pages = _pages(base64.b64decode(render(deps, blocks, mode="pdf")["pdf_base64"]))
    assert len(pages) >= 3
    for i, page in enumerate(pages, start=1):
        t = page.extract_text()
        assert "Alpha project" in t and "Version 2" in t
        assert re.search(rf"\b{i}\b", t)


# preview and PDF are the same HTML apart from page features
def test_preview_is_html_only(deps):
    result = render(deps, [block("free_text", text="x")], mode="preview")
    assert "html" in result and "pdf_base64" not in result
