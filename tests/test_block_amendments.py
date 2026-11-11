"""The Amendments block. Database tests on the bed."""
import pytest

from conftest import block, render, render_one, section, status_of, text

pytestmark = pytest.mark.db


def test_amendments_block_lists_card_and_checklist_amendments(deps, revised_card, amended_checklist):
    t, s, node, _ = render_one(deps, "amendments", card_revision=2)
    assert s["status"] == "ok"
    rows = [[" ".join(c.get_text(" ").split()) for c in tr.find_all("td")] for tr in node.find("tbody").find_all("tr")]
    assert ["2026-09-12", "AI card, revision 2", "The description named the wrong market", "carol"] in rows
    assert any(r[1] == "Transparency checklist, version 2" and r[2] == "A question was misread" and r[3] == "dana"
               for r in rows)
    assert [th.get_text() for th in node.find("thead").find_all("th")] == ["Date", "What", "Reason", "Requested by"]


def test_amendments_block_omitted_when_none(deps):
    b = block("amendments")
    result = render(deps, [b])
    assert f"block-{b['instance_id']}" not in result["html"]
    assert status_of(result, b["instance_id"])["status"] == "empty"


def test_amendments_up_to_pinned_revision_only(deps, revised_card):
    b = block("amendments")
    omitted = render(deps, [b], card_revision=1)
    assert f"block-{b['instance_id']}" not in omitted["html"]
    t, *_ = render_one(deps, "amendments", card_revision=2)
    assert "revision 2" in t


def test_amendment_texts_are_escaped(deps, bed, amended_checklist):
    from conftest import report_bed, IDS
    bed.psql(report_bed.project_db(IDS["A"]), "UPDATE controls.submission SET amend_reason = '<b>x</b>' WHERE id = 'sub-2'")
    t, _, node, _ = render_one(deps, "amendments")
    assert "<b>x</b>" in t and node.find("b") is None
