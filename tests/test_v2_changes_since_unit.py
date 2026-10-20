"""Unit tests on fake data for the corners of changes_since the frozen seed cannot reach: the 300-character
cut, "No change." and the all-unchanged sentence, the 200-row cap, and gaps in version numbers. No database."""
from conftest import need

M = "report_renderer.blocks.changes_since"


def en(msgid, **params):
    from aisc_report_plugin_interface.i18n import fill

    return fill(msgid, params)


def test_cut_keeps_300_characters_then_dots():
    cut = need(M, "cut")
    assert cut("a" * 300) == "a" * 300
    assert cut("a" * 301) == "a" * 300 + "..."
    assert cut(None) == ""


def test_previous_is_the_highest_number_below_with_gaps():
    previous_version = need(M, "previous_version")
    older = [{"pid": "p1", "number": 1}, {"pid": "p4", "number": 4}, {"pid": "p2", "number": 2}]
    assert previous_version(older)["pid"] == "p4"
    assert previous_version([]) is None


def test_at_most_200_test_rows_then_and_k_more():
    compare_metrics = need(M, "compare_metrics")
    before = {("T", f"m{i:03d}"): float(i) for i in range(250)}
    after = {("T", f"m{i:03d}"): float(i) + 1 for i in range(250)}
    rows, more = compare_metrics(before, after, show_unchanged=False)
    assert len(rows) == 200 and more == 50
    assert rows[0]["metric"] == "m000" and rows[0]["change"] == "+1"


def test_unchanged_metrics_are_left_out_unless_asked():
    compare_metrics = need(M, "compare_metrics")
    before = {("T", "a"): 0.5, ("T", "b"): 0.25}
    after = {("T", "a"): 0.5, ("T", "b"): 0.5, ("U", "c"): 1.0}
    rows, more = compare_metrics(before, after, show_unchanged=False)
    assert [(r["tool"], r["metric"]) for r in rows] == [("T", "b"), ("U", "c")]
    assert rows[1]["before"] is None and rows[1]["after"] == 1.0
    rows, _ = compare_metrics(before, after, show_unchanged=True)
    assert [(r["tool"], r["metric"]) for r in rows] == [("T", "a"), ("T", "b"), ("U", "c")]


def test_a_part_without_change_says_no_change():
    part_html = need(M, "part_html")
    html = part_html("tests", "Tests", "", t=en)
    assert 'data-changes="tests"' in html and "No change." in html


def test_every_part_unchanged_gives_one_sentence():
    summary_line = need(M, "summary_line")
    assert summary_line([False, False], base=3, this=5, t=en) == \
        "No changes between version 3 and version 5 in the selected parts."
    assert summary_line([False, True], base=3, this=5, t=en) is None


# a risk is compared by its rating
def test_risk_rating_changes_and_unchanged_ratings():
    from types import SimpleNamespace

    block = need(M, "ChangesSinceBlock")()
    ctx = SimpleNamespace(t=en, data=SimpleNamespace(objectives={}))

    def side(**ratings):
        return {"ids": [], "coverage": {},
                "risks": {rid: {"label": rid.lower(), "rating": v} for rid, v in ratings.items()}}

    before = side(**{"R-1": 9, "R-2": None, "R-3": 12, "R-4": 6, "R-5": None})
    after = side(**{"R-1": 20, "R-2": 12, "R-3": 12, "R-4": None, "R-5": None})
    html, changed = block._diff_objectives(before, after, 1, 2, True, ctx)
    assert changed
    assert "r-1: rating 9 to 20" in html
    assert "r-2: not rated to rating 12" in html
    assert "r-4: rating 6 to not rated" in html
    assert "Unchanged: r-3: rating 12" in html
    assert "Unchanged: r-5: not rated" in html
    assert "severity" not in html


def test_a_change_past_the_200th_metric_row_still_counts_as_a_change():
    """`changed` was read from the first 200 rows only, so with 250 unchanged pairs and
    one change at m240 the tests part counted as unchanged ("No changes between ...")."""
    from types import SimpleNamespace

    from report_renderer.blocks.changes_since import ChangesSinceBlock

    before = {("T", f"m{i:03d}"): 0.5 for i in range(250)}
    after = dict(before)
    after[("T", "m240")] = 0.75
    ctx = SimpleNamespace(t=en, number=lambda v: v)
    side = lambda means: {"counts": {"T": 1}, "means": means}  # noqa: E731
    html, has_change = ChangesSinceBlock()._diff_tests(side(before), side(after), 1, 2, True, ctx)
    assert has_change is True
    assert "and 50 more" in str(html)
