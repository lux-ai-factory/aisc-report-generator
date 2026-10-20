"""End to end on the renderer: project Echo has two versions,
a card each, an objectives assessment each, one evaluation per version with measurements, one
checklist with answers of both versions, and one chart with a comment. A layout with every block
type in a chosen order is rendered as HTML and as PDF; blocks come out in that order and show only
the pinned version's data, with the newer-results notice where it applies.
"""
import base64
import io

import pytest

from conftest import IDS, block, render, soup, text

pytestmark = pytest.mark.db


def layout():
    return [
        block("cover", report_title="Echo end-to-end"),
        block("summary_coverage", title="S-Summary",
              links=[{"objective_id": "R1.1", "tests": ["LangBiTe"], "checklists": ["cl-e"]}]),
        block("free_text", title="S-Text", text="Written by the editor."),
        block("dashboard_chart", title="S-Chart", chart_id=IDS["CHART_E"]),
        block("control_answers", title="S-Answers"),
        block("test_results", title="S-Tests"),
        block("risk_classification", title="S-Risk"),
        block("ai_card", title="S-Card"),
        block("control_objectives", title="S-Objectives"),
    ]


DATA_BLOCKS = ("summary_coverage", "control_answers", "test_results", "risk_classification", "ai_card",
               "control_objectives")


def test_e2e_every_block_in_order_version_2_only(deps):
    blocks = layout()
    result = render(deps, blocks, project="E", system="E_V2")
    html = result["html"]
    ids = [s.get("id") for s in soup(html).find_all("section", class_="block")]
    assert ids == [f"block-{b['instance_id']}" for b in blocks]
    assert [s["block_type"] for s in result["block_statuses"]] == [b["block_type"] for b in blocks]
    assert "E1MARK" not in html
    for marker in ("echo card E2MARK", "Echo risk E2MARK", "accuracy_E2MARK", "Answer E2MARK", "Echo comment",
                   "Written by the editor."):
        assert marker in html, marker
    assert "is newer" not in html and "Newer results exist" not in html
    assert all(s["status"] != "stale" for s in result["block_statuses"])
    assert all(s["status"] != "error" for s in result["block_statuses"]), result["block_statuses"]


def test_e2e_pinned_to_version_1_says_version_2_is_newer(deps):
    blocks = layout()
    result = render(deps, blocks, project="E", system="E_V1")
    html = result["html"]
    assert "E2MARK" not in html
    assert "This report covers version 1. Version 2 is newer." in text(soup(html))
    by_type = {s["block_type"]: s for s in result["block_statuses"]}
    for t in ("control_answers", "test_results", "ai_card", "control_objectives"):
        assert by_type[t]["status"] == "stale", t
        assert "Newer results exist for version 2." in by_type[t]["notices"]
    assert by_type["free_text"]["status"] == "ok"


def test_e2e_the_pdf_has_the_blocks_in_order(deps):
    pytest.importorskip("weasyprint")
    from pypdf import PdfReader

    blocks = layout()
    result = render(deps, blocks, project="E", system="E_V2", mode="pdf")
    pdf = base64.b64decode(result["pdf_base64"])
    full = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    titles = ["S-Summary", "S-Text", "S-Chart", "S-Answers", "S-Tests", "S-Risk", "S-Card", "S-Objectives"]
    # the table of contents lists them first; the sections follow in the same order
    last = [full.rindex(t) for t in titles]
    assert last == sorted(last)
    assert "E1MARK" not in full and "E2MARK" in full
