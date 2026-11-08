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


def test_questions_in_order_with_answer_and_score(deps):
    t, *_ = render_one(deps, "control_answers")
    order = [t.index(q) for q in ("Is the system documented?", "Are deployers told the limits?",
                                  "Are instructions for use written?", "Is the log kept?")]
    assert order == sorted(order)
    assert "Documented in the manual" in t


def test_the_table_has_no_article_column(deps):
    t, _, node, _ = render_one(deps, "control_answers")
    headers = [th.get_text(strip=True) for th in node.find("table").find_all("th")]
    assert headers[:2] == ["Question", "Answer"] and "Article" not in headers
    assert "Art. 13(1)" not in t


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
    assert "Is the system documented?" not in t and "Art. 13(1) as it was" not in t      # no article column
    assert "Kept after removal" in t and "Art. 99" not in t and "LOSTMARK" not in t
    assert "answered 2 of 5" in t and "3.5" in t
    assert "Answered under template revision 7" in t


def test_a_draft_says_no_template_revision(deps):
    t, *_ = render_one(deps, "control_answers")
    assert "template revision" not in t


# Proof files: each question lists the files that prove its answer, never the files themselves
@pytest.fixture
def proof_files(bed):
    """Two files on sub-2's answer to q1 (version 2), one on its answer to q3 (given for version 1, so not
    shown), and on archived sub-3 an answer row to q2 that holds only a file (no answer, no score, no version).
    Undone after the test."""
    db = report_bed.project_db(IDS["A"])
    bed.psql(db, f"""
        INSERT INTO controls.submission_answer (id, "submissionId", "questionId", answer, score, system_version_pid,
               system_version_number, answered_at)
        VALUES ('a-files-only', 'sub-3', 'q2', NULL, NULL, NULL, NULL, NULL);
        INSERT INTO controls.submission_answer_file (id, answer_id, file_id, name, mime, size, sha256, uploaded_by,
               uploaded_at) VALUES
          ('f-1', 'a-2', '5b7f0b1e-1d7e-4c7a-9a43-0c1f5d0b9e11', 'policy.pdf', 'application/pdf', 2048,
           '{"ab" * 32}', 'alice@example.org', '2026-11-01 09:30:00+00'),
          ('f-2', 'a-2', '5b7f0b1e-1d7e-4c7a-9a43-0c1f5d0b9e12', 'Register <b>v2</b>.xlsx',
           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 30000, '{"cd" * 32}', NULL,
           '2026-11-01 10:00:00+00'),
          ('f-3', 'a-4', '5b7f0b1e-1d7e-4c7a-9a43-0c1f5d0b9e13', 'OLDVERSIONFILE.pdf', 'application/pdf', 10,
           '{"ef" * 32}', 'bob', '2026-10-01 10:00:00+00'),
          ('f-4', 'a-files-only', '5b7f0b1e-1d7e-4c7a-9a43-0c1f5d0b9e14', 'screenshot.png', 'image/png', 512,
           '{"01" * 32}', 'carol', '2026-11-01 11:00:00+00');
    """)
    try:
        yield
    finally:
        bed.psql(db, """
            DELETE FROM controls.submission_answer_file WHERE id IN ('f-1', 'f-2', 'f-3', 'f-4');
            DELETE FROM controls.submission_answer WHERE id = 'a-files-only';
        """)


def test_each_answer_lists_its_proof_files(deps, proof_files):
    t, *_ = render_one(deps, "control_answers")
    for expected in ("policy.pdf", "application/pdf", "2.0 KB", "alice@example.org", "2026-11-01 09:30", "ab" * 32,
                     "29 KB", "uploader not recorded"):
        assert expected in t, expected
    assert t.index("policy.pdf") < t.index("Are deployers told the limits?")          # under its own question


def test_the_files_of_an_answer_given_for_another_version_are_not_shown(deps, proof_files):
    t, *_ = render_one(deps, "control_answers")
    assert "OLDVERSIONFILE" not in t


def test_a_question_whose_answer_holds_only_files_is_unanswered_and_lists_them(deps, proof_files):
    t, s, *_ = render_one(deps, "control_answers", include_archived=True)
    assert "screenshot.png" in t and "carol" in t
    assert "answered 1 of 4" in t
    assert not any("other versions" in n for n in s["notices"])


def test_a_file_name_is_text_not_markup(deps, proof_files):
    _, _, node, _ = render_one(deps, "control_answers")
    assert "Register <b>v2</b>.xlsx" in text(node)
    assert node.find("b", string="v2") is None


def test_a_project_without_proof_files_lists_none(deps):
    t, *_ = render_one(deps, "control_answers")
    assert "Proof files" not in t


# Column widths: the table is laid out fixed, so without widths the three columns take a third each and the
# Score column, holding one number, is as wide as the answers.

def _widths():
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "report_renderer/templates/report.css").read_text()
    return {name: float(w) for name, w in re.findall(r"table\.answers col\.(\w+)\s*\{\s*width:\s*([\d.]+)%", css)}


def test_the_table_names_its_columns(deps):
    _, _, node, _ = render_one(deps, "control_answers")
    assert [c.get("class") for c in node.find("table").find_all("col")] == [["question"], ["answer"], ["score"]]


def test_without_scores_there_is_no_score_column(deps):
    _, _, node, _ = render_one(deps, "control_answers", show_scores=False)
    assert [c.get("class") for c in node.find("table").find_all("col")] == [["question"], ["answer"]]


def test_the_score_column_is_narrow_and_the_answer_the_widest():
    w = _widths()
    assert w["score"] <= 10 and w["answer"] > w["question"] and w["question"] + w["answer"] + w["score"] == 100


# Which submission of each checklist is printed: the latest by default, or the ones picked in the layout
# (option `submissions`); a checklist none of whose submissions is picked prints its latest.

def test_the_submissions_option_defaults_to_the_latest_of_each_checklist(deps):
    block = deps.registry.block("control_answers")
    assert block.default_options["submissions"] == "all"
    prop = block.options_schema["properties"]["submissions"]
    assert prop["x-aisc-reference"] is True and prop["x-aisc-all-label"] == "Latest of each checklist"


def test_a_picked_submission_is_printed_instead_of_the_latest(deps):
    t, *_ = render_one(deps, "control_answers", submissions=["sub-3"])
    assert "Archived answer ARCHMARK" in t and "Archived pass ARCHMARK" in t
    assert "Second pass" not in t and "Documented in the manual" not in t


def test_a_checklist_without_a_picked_submission_prints_its_latest(deps):
    t, *_ = render_one(deps, "control_answers", system="A_V1", submissions=["sub-1"])
    assert "First pass" in t and "Yes V1MARK" in t and "Second pass" not in t
    assert "Oversight pass" in t and "Oversight V1MARK" in t


def test_a_picked_submission_not_in_the_project_is_named_in_a_notice(deps):
    _, s, *_ = render_one(deps, "control_answers", submissions=["sub-nowhere"])
    assert "1 selected submission is not in this project or has no answers for this version and is not shown." \
        in s["notices"]


def test_submission_choices_are_the_submissions_with_answers_for_the_version(deps):
    ctx = need("report_renderer.context", "context_for")(IDS["A"], IDS["A_V2"], deps=deps, mode="preview")
    got = deps.registry.block("control_answers")().choices(ctx, "submissions")
    assert [c["value"] for c in got] == ["sub-3", "sub-2"]
    labels = {c["value"]: c["label"] for c in got}
    assert labels["sub-2"].startswith("Transparency checklist · Second pass · version 2 · Draft · ")
    assert labels["sub-3"].startswith("Transparency checklist · Archived pass ARCHMARK · version 3 · Closed, archived · ")


@pytest.fixture
def same_version_later(bed):
    """sub-6: a second submission of cl-1 with the same version number as sub-2, made later, answered for v2."""
    db = report_bed.project_db(IDS["A"])
    bed.psql(db, f"""
        INSERT INTO controls.submission (id, "checklistId", label, status, version, created_at, updated_at)
        VALUES ('sub-6', 'cl-1', 'Made later LATERMARK', 'Closed', 2, now() + interval '1 hour', now());
        INSERT INTO controls.submission_answer (id, "submissionId", "questionId", answer, score, system_version_pid,
               system_version_number, answered_at)
        VALUES ('a-later', 'sub-6', 'q1', 'Later answer', 3, '{IDS["A_V2"]}', 2, now());
    """)
    try:
        yield
    finally:
        bed.psql(db, "DELETE FROM controls.submission_answer WHERE id = 'a-later';"
                     " DELETE FROM controls.submission WHERE id = 'sub-6';")


def test_of_two_submissions_with_the_same_version_the_later_one_is_the_latest(deps, same_version_later):
    t, *_ = render_one(deps, "control_answers")
    assert "Made later LATERMARK" in t and "Second pass" not in t
