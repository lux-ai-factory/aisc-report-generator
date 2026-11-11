"""A report pins a card revision: the snapshot key, and the card readers. Database tests on the bed."""
import pytest

from conftest import IDS, need, render_one, snapshot

pytestmark = pytest.mark.db


def _problems(snap):
    return need("report_renderer.snapshot", "validate")(snap)


def test_snapshot_without_card_revision_reads_revision_one(deps):
    assert _problems(snapshot([])) == []
    info = need("report_renderer.context", "ReportInfo")
    assert info(layout_id=None, layout_name="", revision=None, requested_by="", coverage_links=()).card_revision == 1


def test_snapshot_card_revision_must_be_positive():
    assert _problems(snapshot([], card_revision=2)) == []
    for bad in (0, -1, "2", 1.5):
        problems = _problems({**snapshot([]), "card_revision": bad})
        assert [p["pointer"] for p in problems] == ["/card_revision"], bad


def _card(sources, revision):
    return need("report_renderer.data.qualification", "card")(IDS["A"], IDS["A_V2"], sources=sources,
                                                               revision=revision)


def test_card_reader_takes_highest_revision_not_above_pin(sources, revised_card):
    assert "REV2MARK" not in _card(sources, 1)["description"]
    assert "REV2MARK" in _card(sources, 2)["description"]
    assert "REV2MARK" in _card(sources, 3)["description"]


def test_a_version_with_only_revision_one_reads_it_whatever_the_pin(sources):
    assert _card(sources, 1)["description"] == "Scores loan files with explanations"
    assert _card(sources, 5)["description"] == "Scores loan files with explanations"


def test_risks_follow_the_pinned_revision(sources, revised_card):
    risks = need("report_renderer.data.qualification", "risks")
    first = risks(IDS["A"], IDS["A_V2"], sources=sources, revision=1)
    second = risks(IDS["A"], IDS["A_V2"], sources=sources, revision=2)
    assert "Historic bias" in [r["vulnerability"] for r in first]
    assert [r["vulnerability"] for r in second] == ["Vulnerability REV2MARK"]


def test_components_and_graph_follow_the_pinned_revision(sources, revised_card):
    q = need("report_renderer.data", "qualification")
    assert len(q.components(IDS["A"], IDS["A_V2"], sources=sources, revision=1)) == 3
    assert q.components(IDS["A"], IDS["A_V2"], sources=sources, revision=2) == []
    assert q.knowledge_graph(IDS["A"], IDS["A_V2"], sources=sources, revision=1) is not None
    assert q.knowledge_graph(IDS["A"], IDS["A_V2"], sources=sources, revision=2) is None


def test_snapshot_pinned_at_needs_a_time_zone():
    assert _problems({**snapshot([]), "pinned_at": "2026-09-30T00:00:00+00:00"}) == []
    for bad in ("2026-09-30T00:00:00", "yesterday", 5):
        assert [p["pointer"] for p in _problems({**snapshot([]), "pinned_at": bad})] == ["/pinned_at"], bad


def test_fingerprint_of_a_snapshot_without_pinned_at_is_unchanged():
    import hashlib
    import json

    fingerprint = need("report_renderer.snapshot", "fingerprint")
    snap = snapshot([])
    raw = json.dumps({k: v for k, v in snap.items() if k not in ("mode", "requested_by", "document")},
                     sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert fingerprint(snap) == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert fingerprint({**snap, "pinned_at": "2026-09-30T00:00:00+00:00"}) != fingerprint(snap)


def test_a_report_pinned_before_a_correction_prints_the_card_as_it_was(deps, corrected_system):
    from conftest import CORRECTION_MARKERS

    for block_type in ("cover", "ai_card"):
        *_, result = render_one(deps, block_type, card_revision=1)
        leaked = [m for m in CORRECTION_MARKERS if m in result["html"]]
        assert not leaked, f"{block_type}: a report pinned to revision 1 shows the correction {leaked}"


def test_a_report_pinned_to_the_correction_prints_it(deps, corrected_system):
    t, *_ = render_one(deps, "cover", card_revision=2)
    assert "FIXEDNAME" in t and "FIXEDPROVIDER" in t and "1.0.1" in t
