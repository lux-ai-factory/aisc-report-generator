"""AI card block. Database tests."""
import pytest

from conftest import assert_no_foreign_data, render_one

pytestmark = pytest.mark.db


def test_the_card_of_the_pinned_version(deps):
    t, s, _, result = render_one(deps, "ai_card")
    for expected in ("Alpha scorer", "Acme AI", "Scores loan files with explanations", "Credit scoring",
                     "Loan officers", "Retail banks"):
        assert expected in t, expected
    assert s["status"] == "ok"
    assert_no_foreign_data(result["html"])


def test_tags(deps):
    t, _, node, _ = render_one(deps, "ai_card")
    for tag in ("scoring", "finance", "b2b", "eu"):
        assert tag in t
    tag_list = node.find("dl", class_="tags")
    assert tag_list is not None
    shown = " ".join(tag_list.get_text(" ").split())
    for tag in ("scoring", "finance", "b2b", "eu"):
        assert tag in shown
    # Hidden tags are checked on the tag list only; "scoring" also sits in the target use case
    # "Credit scoring", which must stay shown.
    t, _, node, _ = render_one(deps, "ai_card", show_tags=False)
    assert node.find("dl", class_="tags") is None
    assert "b2b" not in t.split() and "eu" not in t.replace(",", " ").split()


def test_components_in_order(deps):
    _, _, node, _ = render_one(deps, "ai_card")
    rows = [" ".join(tr.get_text(" ").split()) for tr in node.find_all("tr")]
    body = [r for r in rows if any(n in r for n in ("Applications 2025", "Gradient model", "Holdout set"))]
    assert [next(n for n in ("Applications 2025", "Gradient model", "Holdout set") if n in r) for r in body] == \
        ["Applications 2025", "Gradient model", "Holdout set"]
    assert "hasTrainingData" in body[0] and "dataset" in body[0] and "train.csv" in body[0]


def test_components_can_be_hidden(deps):
    t, *_ = render_one(deps, "ai_card", show_components=False)
    assert "Gradient model" not in t


def test_graph_stats(deps):
    t, *_ = render_one(deps, "ai_card", show_graph_stats=True)
    assert "0123456789ab" in t and "0123456789abc" not in t
    assert "2026-09-08" in t
    assert " 4 " in f" {t} " and " 7 " in f" {t} "
    t, *_ = render_one(deps, "ai_card")
    assert "0123456789ab" not in t


def test_no_card_for_the_version(deps):
    t, s, _, _ = render_one(deps, "ai_card", project="C", system="C_V1")
    assert s["status"] == "empty"
    assert "No AI card for version 1." in t


def test_a_newer_card_makes_the_block_stale(deps):
    t, s, _, result = render_one(deps, "ai_card", system="A_V1")
    assert s["status"] == "stale"
    assert "Newer results exist for version 2." in s["notices"]
    assert "Scores loan files V1MARK" in t and "with explanations" not in t


def test_the_latest_card_is_not_stale(deps):
    _, s, _, _ = render_one(deps, "ai_card")  # v3 exists but has no card
    assert s["status"] == "ok"
