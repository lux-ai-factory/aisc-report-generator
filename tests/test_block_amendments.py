"""The Amendments block. Database tests on the bed."""
import pytest

from conftest import IDS, PINNED_AFTER_AMENDMENTS as LATER, block, render, render_one, report_bed, status_of

pytestmark = pytest.mark.db


def _rows(node):
    return [[" ".join(c.get_text(" ").split()) for c in tr.find_all("td")] for tr in node.find("tbody").find_all("tr")]


def test_amendments_block_lists_card_and_checklist_amendments(deps, revised_card, amended_checklist):
    t, s, node, _ = render_one(deps, "amendments", card_revision=2, pinned_at=LATER)
    assert s["status"] == "ok"
    rows = _rows(node)
    assert ["2026-09-12", "AI card, revision 2", "The description named the wrong market", "carol"] in rows
    assert ["2026-09-15", "Transparency checklist, version 2", "A question was misread", "dana"] in rows
    assert [th.get_text() for th in node.find("thead").find_all("th")] == ["Date", "What", "Reason", "Requested by"]


def test_amendments_block_omitted_when_none(deps):
    b = block("amendments")
    result = render(deps, [b], pinned_at=LATER)
    assert f"block-{b['instance_id']}" not in result["html"]
    assert status_of(result, b["instance_id"])["status"] == "empty"


def test_amendments_up_to_pinned_revision_only(deps, revised_card):
    b = block("amendments")
    omitted = render(deps, [b], card_revision=1)
    assert f"block-{b['instance_id']}" not in omitted["html"]
    t, *_ = render_one(deps, "amendments", card_revision=2)
    assert "revision 2" in t


def test_a_checklist_amendment_after_pinned_at_is_not_listed(deps, amended_checklist):
    b = block("amendments")
    result = render(deps, [b], pinned_at="2026-09-14T00:00:00+00:00")
    assert f"block-{b['instance_id']}" not in result["html"]


def test_without_pinned_at_no_checklist_amendment_is_listed(deps, amended_checklist):
    b = block("amendments")
    assert f"block-{b['instance_id']}" not in render(deps, [b])["html"]


def test_an_archived_amendment_is_listed_only_when_asked(deps, bed, amended_checklist):
    bed.psql(report_bed.project_db(IDS["A"]), "UPDATE controls.submission SET archived_at = now() WHERE id = 'sub-2'")
    b = block("amendments")
    assert f"block-{b['instance_id']}" not in render(deps, [b], pinned_at=LATER)["html"]
    t, *_ = render_one(deps, "amendments", pinned_at=LATER, include_archived=True)
    assert "Transparency checklist, version 2" in t


def test_amendment_texts_are_escaped(deps, bed, amended_checklist):
    bed.psql(report_bed.project_db(IDS["A"]), "UPDATE controls.submission SET amend_reason = '<b>x</b>' WHERE id = 'sub-2'")
    t, _, node, _ = render_one(deps, "amendments", pinned_at=LATER)
    assert "<b>x</b>" in t and node.find("b") is None
