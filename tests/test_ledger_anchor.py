"""A generated report prints the ledger anchor the composer sent (snapshot document.ledger_anchor:
the project log's newest entry when the report was made), on every page, as
"Ledger entry <seq> · <first 16 hex digits of its sha256>". verify-ledger-export.py --anchor takes that
text as it is printed. Without an anchor (the ledger off) nothing is printed and the document is
unchanged. A preview never prints one: it is not a generated document."""
import re

import pytest

from v2_core_helpers import blk, do_render, pdf_pages, snap

pytestmark = pytest.mark.db
DOC_ID = "3c9d1f2e-7a6b-4c5d-8e9f-0a1b2c3d4e5f"
ANCHOR = {"seq": 41, "entry_sha256": "0123456789abcdef" + "ab" * 24}
PRINTED = "Ledger entry 41 · 0123456789abcdef"


def test_a_generated_report_prints_its_anchor_on_every_page(deps):
    blocks = [blk("free_text", text="one"), blk("free_text", text="two", page_break_before=True)]
    pages = pdf_pages(do_render(deps, snap(blocks, mode="pdf", document={"id": DOC_ID, "ledger_anchor": ANCHOR})))
    assert len(pages) >= 2
    for p in pages:
        assert re.search(r"Ledger entry 41 · 0123456789abcdef", p), p[-300:]


def test_beside_the_document_id_line(deps):
    s = snap([blk("free_text", text="x")], mode="pdf", style={"font": "inter", "font_size_pt": 10,
                                                             "primary_color": "#000fdf", "accent_color": "#ff007e",
                                                             "show_document_id": True},
             document={"id": DOC_ID, "ledger_anchor": ANCHOR})
    page = pdf_pages(do_render(deps, s))[0]
    assert "Document 3c9d1f2e" in page and PRINTED in page


def test_without_an_anchor_nothing_is_printed(deps):
    page = pdf_pages(do_render(deps, snap([blk("free_text", text="x")], mode="pdf", document={"id": DOC_ID})))[0]
    assert "Ledger entry" not in page


def test_a_preview_prints_no_anchor(deps):
    html = do_render(deps, snap([blk("free_text", text="x")], document={"id": None, "ledger_anchor": ANCHOR}))["html"]
    assert "Ledger entry" not in html


def test_an_anchor_that_is_not_one_is_refused(deps):
    from report_renderer.document import InvalidSnapshot

    with pytest.raises(InvalidSnapshot):
        do_render(deps, snap([blk("free_text", text="x")], mode="pdf",
                             document={"id": DOC_ID, "ledger_anchor": {"seq": "41", "entry_sha256": "zz"}}))


def test_the_anchor_is_not_part_of_the_fingerprint(deps):
    """The fingerprint is of what the report says, not of when it was made (the snapshot's document is left out)."""
    blocks = [blk("free_text", text="x")]
    a = do_render(deps, snap(blocks, mode="pdf", document={"id": DOC_ID}))
    b = do_render(deps, snap(blocks, mode="pdf", document={"id": DOC_ID, "ledger_anchor": ANCHOR}))
    assert a["fingerprint"] == b["fingerprint"]
