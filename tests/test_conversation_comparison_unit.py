"""The comparison of conversations a report draws: the rules of the results dashboard's SQL, on a run's Conversation
results. No database."""
from report_renderer.conversations import CONVERSATION_METRIC, Compared, compare, without_conversations


def talk(category, community, slot, scenario="P1", register="basic", language="en", orgs="", repetition=1):
    d = {"category": category, "community": community, "scenario": scenario, "register": register,
         "language": language, "repetition": repetition, "organisations": orgs,
         "outcome": "referral" if orgs else "no referral"}
    if slot is not None:
        d["slot"] = slot
    return {"name": CONVERSATION_METRIC, "metric": CONVERSATION_METRIC, "score": 1.0 if orgs else 0.0, "dimensions": d}


def base(**kw):
    return talk("BASELINE", "-", None, **kw)


def test_a_person_sent_where_the_baseline_was_sent_counts_as_the_same():
    c = compare([("OpenAI", [base(orgs="A"), talk("AGE", "18", 0, orgs="A"), talk("AGE", "70", 1, orgs="B")])])
    assert c.overall == {"OpenAI": (0.5, 2)}


def test_the_organisations_are_compared_as_a_set():
    c = compare([("OpenAI", [base(orgs="A | B"), talk("AGE", "18", 0, orgs=" b | a | A ")])])
    assert c.overall["OpenAI"] == (1.0, 1)


def test_no_referral_on_both_sides_counts_as_the_same_and_on_one_side_does_not():
    c = compare([("Local", [base(orgs=""), talk("AGE", "18", 0, orgs=""), talk("AGE", "70", 1, orgs="B")])])
    assert c.overall["Local"] == (0.5, 2)


def test_a_person_is_paired_with_the_baseline_of_the_same_question_only():
    c = compare([("OpenAI", [base(orgs="A", register="basic"), base(orgs="B", register="broken"),
                             talk("AGE", "18", 0, register="basic", orgs="B"),
                             talk("AGE", "18", 0, register="broken", orgs="B")])])
    assert c.overall["OpenAI"] == (0.5, 2)


def test_a_baseline_of_another_run_is_never_used():
    c = compare([("OpenAI", [base(orgs="A"), talk("AGE", "18", 0, orgs="A")]),
                 ("OpenAI", [base(orgs="B"), talk("GENDER", "male", 0, orgs="A")])])
    assert c.overall["OpenAI"] == (0.5, 2)


def test_two_models_are_kept_apart():
    c = compare([("OpenAI", [base(orgs="A"), talk("AGE", "18", 0, orgs="A")]),
                 ("Local", [base(orgs="A"), talk("AGE", "18", 0, orgs="B")])])
    assert c.overall == {"OpenAI": (1.0, 1), "Local": (0.0, 1)}


def test_runs_with_no_conversation_results_give_an_empty_comparison():
    c = compare([("OpenAI", [{"name": "Overall Pass Rate", "score": 0.0, "dimensions": None}])])
    assert isinstance(c, Compared) and not c.overall


def test_a_conversation_without_its_baseline_is_left_out_of_the_comparison_with_the_baseline():
    c = compare([("OpenAI", [talk("AGE", "18", 0, orgs="A")])])
    assert c.overall == {}


def test_the_other_results_stay_when_the_conversations_are_taken_out():
    other = {"name": "Overall Pass Rate", "score": 0.0}
    assert without_conversations([talk("AGE", "18", 0), other]) == ([other], 1)


def test_a_run_with_a_text_slot_and_a_missing_slot_is_still_compared():
    c = compare([("OpenAI", [base(orgs="A"), talk("AGE", "18", "a", orgs="A"), talk("AGE", "70", None, orgs="B")])])
    assert c.overall == {"OpenAI": (0.5, 2)}
