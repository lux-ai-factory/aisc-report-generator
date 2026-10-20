"""The promptfoo section: Pass and Fail as the tool's own shares, the headline and English wording.

promptfoo's own results are shares: pass_rate (tests that passed all of their assertions) and fail_rate. The
report labels them Pass and Fail with a note saying so, derives no counts from them and makes no verdict.
"""
import re

import fixtures as F
from conftest import ctx, need, soup, text

P = "aisc_report_plugin_promptfoo"
NOTE = ("Pass and Fail are promptfoo's own results: a test passes when all of its assertions pass. "
        "The values are shares of the tests.")


def cls():
    return need(P, "PROMPTFOOToolRenderer")


def render(run=None, **opts):
    return cls()().render(run or F.run(), ctx(**opts))


def labels(html):
    out = []
    for tr in soup(html).find_all("tr"):
        cells = [text(c) for c in tr.find_all(["th", "td"])]
        if len(cells) >= 2:
            out.append(cells[0])
    return out


def test_rows_are_labelled_pass_and_fail():
    ls = labels(render())
    assert "Pass (higher is better)" in ls and "Fail (lower is better)" in ls, ls
    assert not any(label.startswith(("Pass rate", "Fail rate")) for label in ls), ls


def test_the_note_says_whose_results_they_are():
    assert NOTE in text(soup(render()))


def test_no_note_when_neither_rate_is_present():
    """Guard (passes today): the note is shown only when pass_rate or fail_rate is present."""
    t = text(soup(render(F.run(F.LATENCY_COST_TESTS, number=3))))
    assert "promptfoo's own results" not in t


def test_chart_series_labels():
    s = cls()().charts(F.run())[0]
    assert [x["label"] for x in s["series"]] == ["Pass", "Fail", "Refusal rate"]
    assert s["title"] == "Pass, fail and refusal rates"


def test_headline_label_is_pass():
    by = {i["label"]: i["value"] for i in cls()().headline(F.run())}
    assert "Pass" in by and "Pass rate" not in by, by
    assert re.fullmatch(r"85(\.0+)?\s?%", by["Pass"])


def test_no_counts_are_derived_from_the_shares():
    """Guard (passes today): shares only, no "34 of 40"."""
    t = text(soup(render()))
    assert not re.search(r"\b\d+ of 40\b", t)


def test_wording():
    html = render()
    t = text(soup(html))
    words = re.findall(r"\b(?:Pass|Fail)\b", t)
    assert words, "missing feature: Pass / Fail labels"
    # Pass and Fail name promptfoo's own results; they are not rates computed by the report
    assert not re.search(r"\b(?:Pass|Fail) rate\b", t), "the words must be the tool's result names"
    for w in ("verdict", "compliant", "unsafe", "worse"):
        assert w not in t.lower(), w
    assert not re.search(r"\bsafe\b", t.lower())
    # "better" appears only inside the unit's own direction words
    assert t.lower().count("better") == t.lower().count("is better")


def test_an_english_context_gives_the_same_headline_as_none():
    """Guard (passes today)."""
    assert cls()().headline(F.run(), ctx=ctx()) == cls()().headline(F.run())
