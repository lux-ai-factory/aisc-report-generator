"""A dashboard chart's comments by the version current when written, and by the report's period.
Alpha's chart 33: comments of 09-12 10:00 (a reply at
11:00) and 09-13 09:00, all under version 2 (09-08 to 09-15); a Beta comment on the same chart id."""
import pytest

from conftest import IDS, window
from v2_block_helpers import one

pytestmark = pytest.mark.db


def _chart(deps, system, selection=None):
    t, _, _, _ = one(deps, "dashboard_chart", project="A", system=system, chart_id=IDS["CHART_A"],
                     show_comments=True, include_replies=True, selection=selection)
    return t


def test_comments_written_under_the_version_are_printed(deps):
    assert "Second root comment" in _chart(deps, "A_V2")


def test_comments_of_another_version_are_not_printed(deps):
    assert "Second root comment" not in _chart(deps, "A_V3")


def test_with_other_versions_they_are_printed_with_their_version(deps):
    t = _chart(deps, "A_V3", window(other_versions=True))
    assert "Second root comment" in t and "(version 2)" in t


def test_the_period_bounds_the_comments(deps):
    t = _chart(deps, "A_V2", window("2026-09-13", "2026-09-14"))
    assert "Second root comment" in t and "First look" not in t


def test_a_reply_follows_its_root(deps):
    t = _chart(deps, "A_V2", window("2026-09-12", "2026-09-13"))
    assert "First look" in t and "Agreed, reply text" in t


def test_comments_of_another_project_never_appear(deps):
    assert "BETAMARK" not in _chart(deps, "A_V2", window(other_versions=True))


def test_the_notice_says_how_comments_are_matched(deps):
    t = _chart(deps, "A_V2")
    assert "Comments are matched to the version current when they were written." in t


@pytest.fixture
def deleted_comment(bed):
    """A comment on Alpha's chart 33 deleted on the dashboard, with a reply to it, and a live one."""
    bed.psql("superset", "INSERT INTO aisc_comment (id, dashboard_id, chart_id, parent_id, author_sub, author_name,"
                         " body, created_at, deleted_at) VALUES"
                         " (901, '10', 33, NULL, 'alice', 'Alice Editor', 'DELETEDMARK root', '2026-09-12 12:00',"
                         "  '2026-09-12 13:00'),"
                         " (902, '10', 33, 901, 'olga', 'Olga Owner', 'DELETEDREPLY reply', '2026-09-12 12:30', NULL),"
                         " (903, '10', 33, NULL, 'olga', 'Olga Owner', 'KEPTMARK live', '2026-09-12 12:45', NULL)")
    yield
    bed.psql("superset", "DELETE FROM aisc_comment WHERE id IN (901, 902, 903)")


def test_a_comment_deleted_on_the_dashboard_is_not_read_nor_printed(deps, deleted_comment):
    """The dashboard soft-deletes a comment (deleted_at) and no longer shows it; the
    report printed its text, author and time, and the replies to it."""
    bodies = [c["body"] for c in _comments(deps)]
    assert "KEPTMARK live" in bodies and "DELETEDMARK root" not in bodies
    t = _chart(deps, "A_V2")
    assert "KEPTMARK" in t
    assert "DELETEDMARK" not in t and "DELETEDREPLY" not in t


def _comments(deps):
    from report_renderer.data import superset_db

    return superset_db.comments(IDS["A"], IDS["A_V2"], sources=deps.sources, chart_id=IDS["CHART_A"])
