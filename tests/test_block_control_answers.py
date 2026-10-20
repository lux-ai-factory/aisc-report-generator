"""Control answers block.

Alpha v2 in its own database: checklist cl-1 has submissions v1 (Closed), v2 (Draft, the latest not
archived with a v2 answer) and v3 (archived); cl-2 has only v1 and v3 answers; cl-3 none.
"""
import pytest

from conftest import IDS, assert_no_foreign_data, need, render_one, text

import report_bed

pytestmark = pytest.mark.db


def test_the_latest_submission_with_answers_for_the_version(deps):
    t, s, node, result = render_one(deps, "control_answers")
    for expected in ("Transparency checklist", "EU AI Act", "Transparency", "Second pass", "Draft"):
        assert expected in t, expected
    assert "Oversight checklist" not in t and "Unanswered checklist" not in t
    assert "ARCHMARK" not in result["html"]
    assert_no_foreign_data(result["html"])


def test_questions_in_order_with_article_answer_and_score(deps):
    t, *_ = render_one(deps, "control_answers")
    order = [t.index(q) for q in ("Is the system documented?", "Are deployers told the limits?",
                                  "Are instructions for use written?", "Is the log kept?")]
    assert order == sorted(order)
    assert "Art. 13(1)" in t and "Documented in the manual" in t


def test_answers_are_escaped(deps):
    _, _, node, result = render_one(deps, "control_answers")
    assert "Partly <b>bold</b>" in text(node)
    assert node.find("b", string="bold") is None


def test_answers_of_other_versions_are_unanswered_here(deps):
    t, s, *_ = render_one(deps, "control_answers")
    assert "2 answers were given for other versions and are not shown." in s["notices"]
    assert t.count("Not answered") == 2


def test_unanswered_questions_can_be_omitted(deps):
    t, *_ = render_one(deps, "control_answers", show_unanswered=False)
    assert "Not answered" not in t and "Are instructions for use written?" not in t


def test_mean_score_and_count(deps):
    t, *_ = render_one(deps, "control_answers")
    assert "2.5" in t and "answered 2 of 4" in t
    t, *_ = render_one(deps, "control_answers", show_scores=False)
    assert "answered 2 of 4" not in t


# include_archived
def test_archived_submissions_on_request(deps):
    t, *_ = render_one(deps, "control_answers", include_archived=True)
    assert "Archived answer ARCHMARK" in t and "answered 1 of 4" in t


def test_checklists_option(deps):
    _, s, *_ = render_one(deps, "control_answers", checklists=["cl-2"])
    assert s["status"] == "empty"


def test_empty_when_nothing_answered_for_the_version(deps):
    _, s, *_ = render_one(deps, "control_answers", system="A_V3", checklists=["cl-1"])
    assert s["status"] == "empty"


def test_no_project_database_is_empty_not_error(deps):
    _, s, *_ = render_one(deps, "control_answers", project="C", system="C_V1")
    assert s["status"] == "empty"


def test_answers_of_a_newer_version(deps):
    _, s, *_ = render_one(deps, "control_answers")
    assert s["status"] == "stale" and "Newer results exist for version 3." in s["notices"]


def test_at_most_1000_answers(deps):
    t, _, node, result = render_one(deps, "control_answers", project="B", system="B_V1")
    assert "and 6 more" in t
    shown = [td for td in node.find_all("td") if td.get_text(strip=True).startswith("Answer ")]
    assert len(shown) <= 1000


def test_checklist_choices_are_of_the_project(deps):
    ctx = need("report_renderer.context", "context_for")(IDS["A"], IDS["A_V2"], deps=deps, mode="preview")
    values = {c["value"] for c in deps.registry.block("control_answers")().choices(ctx, "checklists")}
    assert "cl-1" in values and "cl-b" not in values and "cl-big" not in values


# A closed submission as it was answered (the controls app's answerSheet.ts)
@pytest.fixture
def archived_closed_with_kept_wording(bed):
    """sub-3 (Closed, archived, the latest with include_archived) answered under template revision 7: its
    answer to q1 keeps the wording it was answered under, one to a question removed since stays (questionId
    NULL) and one with neither its wording nor its question is left out. Undone after the test."""
    db = report_bed.project_db(IDS["A"])
    bed.psql(db, f"""
        UPDATE controls.submission SET questions_version = 7 WHERE id = 'sub-3';
        UPDATE controls.submission_answer SET question_text = 'Was the system documented then?',
               question_article = 'Art. 13(1) as it was', question_category = 'info', question_order = 1
         WHERE id = 'a-6';
        INSERT INTO controls.submission_answer (id, "submissionId", "questionId", answer, score, system_version_pid,
               system_version_number, answered_at, question_text, question_article, question_category, question_order)
        VALUES ('a-removed', 'sub-3', NULL, 'Kept after removal', 2, '{IDS["A_V2"]}', 2, now(),
                'Was a question removed since?', 'Art. 99', 'gone', 5),
               ('a-lost', 'sub-3', NULL, 'Lost LOSTMARK', 1, '{IDS["A_V2"]}', 2, now(), NULL, NULL, NULL, NULL);
    """)
    try:
        yield
    finally:
        bed.psql(db, """
            DELETE FROM controls.submission_answer WHERE id IN ('a-removed', 'a-lost');
            UPDATE controls.submission_answer SET question_text = NULL, question_article = NULL,
                   question_category = NULL, question_order = NULL WHERE id = 'a-6';
            UPDATE controls.submission SET questions_version = NULL WHERE id = 'sub-3';
        """)


def test_a_closed_submission_shows_its_answers_as_they_were_answered(deps, archived_closed_with_kept_wording):
    t, *_ = render_one(deps, "control_answers", include_archived=True)
    order = [t.index(q) for q in ("Was the system documented then?", "Are deployers told the limits?",
                                  "Are instructions for use written?", "Is the log kept?",
                                  "Was a question removed since?")]
    assert order == sorted(order)
    assert "Is the system documented?" not in t and "Art. 13(1) as it was" in t
    assert "Kept after removal" in t and "Art. 99" in t and "LOSTMARK" not in t
    assert "answered 2 of 5" in t and "3.5" in t
    assert "Answered under template revision 7" in t


def test_a_draft_says_no_template_revision(deps):
    t, *_ = render_one(deps, "control_answers")
    assert "template revision" not in t
