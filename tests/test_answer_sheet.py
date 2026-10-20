"""The questions a submission shows, with its answers: the controls app's rule
(apps/controls/src/lib/answerSheet.ts), as the report reads it.

A draft follows the template: today's questions. A closed submission shows each question it answered as it
was when it was closed (the wording its answer keeps), an answer to a question removed since included; the
template's questions it left unanswered are shown as they are now. An answer closed before the wording was
kept takes today's, and is left out when its question is gone too.
"""
from conftest import need

TODAY = [
    {"id": "q1", "position": 1, "text": "Is it documented?", "article": "Art. 13"},
    {"id": "q2", "position": 2, "text": "Is the log kept?", "article": "Art. 12"},
    {"id": "q3", "position": 3, "text": "Can it be halted?", "article": None},
]


def answer(id_, question_id, *, text=None, article=None, order=None, value="yes"):
    return {"id": id_, "question_id": question_id, "answer": value, "question_text": text,
            "question_article": article, "question_order": order}


def sheet(status, answers, questions=TODAY):
    rows = need("report_renderer.views", "answer_sheet")(status, questions, answers)
    return [(q["text"], q["article"], q["position"], a["id"] if a else None) for q, a in rows]


def test_a_draft_follows_todays_questions():
    answers = [answer("a1", "q1", text="Was it documented?", article="Art. 13 old", order=1),
               answer("a2", None, text="A removed question", order=9)]
    assert sheet("Draft", answers) == [("Is it documented?", "Art. 13", 1, "a1"),
                                       ("Is the log kept?", "Art. 12", 2, None),
                                       ("Can it be halted?", None, 3, None)]


def test_a_closed_submission_shows_each_answered_question_as_it_was_when_closed():
    answers = [answer("a1", "q1", text="Was it documented?", article="Art. 13 old", order=1)]
    assert sheet("Closed", answers) == [("Was it documented?", "Art. 13 old", 1, "a1"),
                                        ("Is the log kept?", "Art. 12", 2, None),
                                        ("Can it be halted?", None, 3, None)]


def test_a_closed_submission_keeps_its_answer_to_a_removed_question_at_its_place():
    answers = [answer("a9", None, text="A removed question", article="Art. 9", order=2)]
    assert sheet("Closed", answers) == [("Is it documented?", "Art. 13", 1, None),
                                        ("A removed question", "Art. 9", 2, "a9"),
                                        ("Is the log kept?", "Art. 12", 2, None),
                                        ("Can it be halted?", None, 3, None)]


def test_an_answer_closed_before_the_wording_was_kept_takes_todays_or_is_left_out():
    answers = [answer("a2", "q2"), answer("a8", None)]
    assert sheet("Closed", answers) == [("Is it documented?", "Art. 13", 1, None),
                                        ("Is the log kept?", "Art. 12", 2, "a2"),
                                        ("Can it be halted?", None, 3, None)]


def test_a_kept_question_without_its_place_takes_todays_place_or_the_first():
    answers = [answer("a3", "q3", text="Could it be halted?"), answer("a7", None, text="Gone, no place")]
    assert sheet("Closed", answers) == [("Gone, no place", None, 0, "a7"),
                                        ("Is it documented?", "Art. 13", 1, None),
                                        ("Is the log kept?", "Art. 12", 2, None),
                                        ("Could it be halted?", None, 3, "a3")]
