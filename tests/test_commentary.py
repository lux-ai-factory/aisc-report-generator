"""Commentary on every block, and light formatting in free text."""
import pytest

from conftest import soup, text
from v2_core_helpers import H, blk, do_render, pdf_pages, service, snap

pytestmark = pytest.mark.db


def sec(html, b):
    node = soup(html).find("section", id=f"block-{b['instance_id']}")
    assert node is not None
    return node


# Placement.

def test_commentary_after_the_block_by_default(deps):
    b = blk("ai_card", commentary="The card was **reviewed** by the DPO.")
    result = do_render(deps, snap([b]))
    node = sec(result["html"], b)
    com = node.find("div", class_="commentary")
    assert com is not None, "missing feature: commentary"
    assert com.find("strong") is not None and text(com.find("strong")) == "reviewed"
    children = [c for c in node.children if getattr(c, "name", None)]
    assert children[-1] is com, "commentary comes after the block's HTML"
    assert [s for s in result["block_statuses"] if s["instance_id"] == b["instance_id"]][0]["status"] == "ok"


def test_commentary_before_sits_between_notices_and_the_block(deps):
    b = blk("test_results", commentary="Read with care.", commentary_position="before")
    node = sec(do_render(deps, snap([b], system="A_V1"))["html"], b)   # v1 has a newer-results notice
    com = node.find("div", class_="commentary")
    assert com is not None, "missing feature: commentary"
    html = str(node)
    notices = node.find("ul", class_="notices")
    assert notices is not None
    assert html.index(str(notices)) < html.index('class="commentary"')
    body = [c for c in node.children if getattr(c, "name", None) and c.name not in ("h2",)
            and c is not notices and c is not com]
    assert body and html.index('class="commentary"') < html.index(str(body[0]))


@pytest.mark.parametrize("value", ["", "   \n  "])
def test_empty_commentary_changes_nothing(deps, value):
    """An empty (after trimming) commentary gives exactly the section without commentary; the option must be accepted."""
    plain, withc = blk("ai_card"), blk("ai_card", commentary=value)
    withc["instance_id"] = plain["instance_id"]
    a = do_render(deps, snap([plain]))
    b = do_render(deps, snap([withc]))
    assert [s["status"] for s in b["block_statuses"]] == ["ok"], "commentary must be a valid common option"
    assert a["html"] == b["html"]


# Shown for empty, stale and error blocks, with the status unchanged.

def test_commentary_on_an_empty_block(deps):
    b = blk("test_results", commentary="No tests were run yet; planned for Q4.")
    result = do_render(deps, snap([b], project="D", system="D_V1"))
    assert result["block_statuses"][0]["status"] == "empty"
    com = sec(result["html"], b).find("div", class_="commentary")
    assert com is not None and "planned for Q4" in text(com)


def test_commentary_on_a_stale_block(deps):
    b = blk("ai_card", commentary="Card of the first release.")
    result = do_render(deps, snap([b], system="A_V1"))
    assert result["block_statuses"][0]["status"] == "stale"
    assert sec(result["html"], b).find("div", class_="commentary") is not None


def test_commentary_on_an_error_block(deps):
    b = blk("dashboard_chart", chart_id=999999, commentary="The chart moved.")
    result = do_render(deps, snap([b]))
    assert result["block_statuses"][0]["status"] == "error"
    com = sec(result["html"], b).find("div", class_="commentary")
    assert com is not None and "The chart moved." in text(com)


# The caption.

def test_the_commentary_has_a_small_caption(deps):
    b = blk("ai_card", commentary="x")
    com = sec(do_render(deps, snap([b]))["html"], b).find("div", class_="commentary")
    assert com is not None and "Commentary" in text(com)


# Free text formats.

def test_free_text_without_format_is_plain_as_today(deps):
    """Compatibility pin: free text without a format stays plain text."""
    b = blk("free_text", text="**not bold** <b>x</b>\nline two\n\npara two")
    node = sec(do_render(deps, snap([b]))["html"], b)
    assert node.find("strong") is None and node.find("b") is None
    assert "**not bold** <b>x</b>" in text(node)
    assert node.find("br") is not None and len(node.find_all("p")) == 2


def test_free_text_format_plain_is_accepted(deps):
    b = blk("free_text", text="**x**", format="plain")
    result = do_render(deps, snap([b]))
    assert result["block_statuses"][0]["status"] == "ok"
    assert sec(result["html"], b).find("strong") is None


def test_free_text_format_markdown(deps):
    b = blk("free_text", format="markdown",
            text="**bold** and *it*\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
                 "[site](https://e.org) [bad](javascript:alert(1)) <script>alert(1)</script>")
    result = do_render(deps, snap([b]))
    assert result["block_statuses"][0]["status"] == "ok"
    node = sec(result["html"], b)
    assert node.find("strong") and node.find("em") and node.find("ul") and node.find("table")
    links = [a["href"] for a in node.find_all("a")]
    assert links == ["https://e.org"]
    assert node.find("script") is None and "<script>alert(1)</script>" in text(node)


# Links in the PDF.

def test_links_are_clickable_in_the_pdf_and_printed_as_their_text(deps):
    import base64
    import io

    from pypdf import PdfReader

    b = blk("free_text", format="markdown", text="See [the example site](https://example.org).")
    result = do_render(deps, snap([b], mode="pdf"))
    pages = pdf_pages(result)
    assert any("the example site" in p for p in pages)
    assert not any("https://example.org" in p for p in pages)
    reader = PdfReader(io.BytesIO(base64.b64decode(result["pdf_base64"])))
    uris = [a.get_object().get("/A", {}).get("/URI") for p in reader.pages for a in (p.get("/Annots") or [])]
    assert "https://example.org" in uris


# new_instance_options.

def test_block_types_return_new_instance_options(deps):
    types = {t["type_id"]: t for t in service(deps).get("/v1/block-types", headers=H).json()}
    for t in types.values():
        assert "new_instance_options" in t, f"missing feature: new_instance_options on {t['type_id']}"
    assert types["free_text"]["new_instance_options"] == {"format": "markdown"}
    assert types["free_text"]["default_options"].get("format") == "plain"
