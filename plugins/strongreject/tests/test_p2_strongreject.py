"""The StrongREJECT section: no pass or fail word, and English only.

StrongREJECT writes harmfulness scores, never a pass or fail, so its section shows none. Reports are English only.
These tests pin behaviour that already holds today (compatibility guards).
"""
import re

import fixtures as F
from conftest import ctx, need, soup, text

P = "aisc_report_plugin_strongreject"


def cls():
    return need(P, "STRONGREJECTToolRenderer")


def test_no_pass_or_fail_word_in_a_scored_run():
    """Guard (passes today): the tool states no pass or fail, so the report shows none."""
    t = text(soup(cls()().render(F.run(), ctx())))
    assert "0.2" in t
    assert not re.search(r"\b(pass|passed|fail|failed)\b", t, re.I), t[:400]


def test_no_pass_or_fail_word_in_a_failed_run():
    """Guard (passes today): "not scored" is not a verdict and no Pass / Fail replaces it."""
    t = text(soup(cls()().render(F.failed_run(), ctx())))
    assert "not scored" in t
    assert not re.search(r"\b(pass|passed|fail|failed)\b", t, re.I), t[:400]


def test_an_english_context_gives_the_same_headline_as_none():
    """Guard (passes today)."""
    assert cls()().headline(F.run(), ctx=ctx()) == cls()().headline(F.run())
