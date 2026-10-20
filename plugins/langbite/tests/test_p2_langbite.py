"""The LangBiTe section: the tool's own Pass / Fail, the headline and English wording.

The report shows LangBiTe's own Pass / Fail (its tolerance check, per group and for the run) and never makes a
verdict of its own. Reports are English only; the package ships an en.json with one singular form.
"""
import json
import re
from pathlib import Path

import fixtures as F
from conftest import I, ctx, need, soup, table_with, text

P = "aisc_report_plugin_langbite"
PKG_DIR = Path(__file__).resolve().parents[1] / P


def cls():
    return need(P, "LANGBITEToolRenderer")


def render(run=None, **opts):
    return cls()().render(run or F.run(), ctx(**opts))


def run_with(all_passed_score, all_passed_description, groups=None):
    return F.run([F.SUMMARY[0], *(F.GROUPS if groups is None else groups), F.SUMMARY[1],
                  F.m("All Tolerances Passed", all_passed_score, all_passed_description)])


# ── Group table: the tool's own check as Pass / Fail ────────────────────────

def test_the_pass_fail_column_follows_the_tolerance_set_column():
    heads, _ = table_with(render(), "Concern")
    assert heads[-2].startswith("Tolerance set in LangBiTe")
    assert heads[-1] == "Pass / Fail (LangBiTe tolerance check)"


def test_realistic_not_evaluated_group_and_other_texts_as_written():
    # LangBiTe writes "Not evaluated" only when no prompt passed or failed (global_evaluation.py:125-128)
    groups = [F.g("ageism", "gpt-4o-mini", "en_us", 0.75, "Passed", "0.8", 3, 1, 4),
              F.g("gender", "gpt-4o-mini", "en_us", 0.6, "Failed", "0.8", 6, 4, 10),
              F.g("hate", "gpt-4o-mini", "en_us", 0.0, "Not evaluated", "0.8", 0, 0, 3),
              F.g("religion", "gpt-4o-mini", "en_us", 0.5, "Unknown", "0.8", 1, 1, 2)]
    _, rows = table_with(render(run_with(0.0, "1/4 tolerance checks passed", groups)), "Concern")
    assert [r[-1] for r in rows] == ["Pass", "Fail", "Not evaluated", "Unknown"]
    assert rows[2][5] == "0 of 3" and rows[2][6] == "0 of 3"


def test_prompt_count_columns_stay():
    _, rows = table_with(render(), "Concern")
    assert rows[1][5] == "9 of 10" and rows[1][6] == "1 of 10"
    assert rows[1][-1] == "Pass"


# ── Run result line ─────────────────────────────────────────────────────────

def test_all_checks_passed_is_pass():
    groups = [F.g("gender", "gpt-4o-mini", "en_us", 0.9, "Passed", "0.8", 9, 1, 10),
              F.g("ageism", "gpt-4o-mini", "en_us", 0.9, "Passed", "0.8", 9, 1, 10),
              F.g("hate", "gpt-4o-mini", "en_us", 0.9, "Passed", "0.8", 9, 1, 10)]
    t = text(soup(render(run_with(1.0, "3/3 tolerance checks passed", groups))))
    assert "All tolerance checks: Pass (3 of 3 passed)" in t


def test_a_failed_check_is_fail():
    t = text(soup(render()))
    assert "All tolerance checks: Fail (1 of 4 passed)" in t


def test_no_group_is_not_evaluated_not_fail():
    # The plugin writes 0.0 with "0/0 tolerance checks passed" when the run produced no group
    t = text(soup(render(run_with(0.0, "0/0 tolerance checks passed", groups=[]))))
    assert "All tolerance checks: not evaluated (0/0 tolerance checks passed)" in t
    assert "All tolerance checks: Fail" not in t


def test_unparsable_description_is_not_evaluated():
    t = text(soup(render(run_with(0.0, "garbage"))))
    assert "All tolerance checks: not evaluated (garbage)" in t


def test_no_line_when_the_measurement_is_absent():
    t = text(soup(render(F.run([F.SUMMARY[0], *F.GROUPS, F.SUMMARY[1]]))))
    assert "Overall pass rate" in t
    assert "All tolerance checks" not in t


def test_the_line_is_shown_with_summary_detail():
    t = text(soup(render(detail="summary")))
    assert "All tolerance checks: Fail (1 of 4 passed)" in t


# ── Headline ────────────────────────────────────────────────────────────────

def test_an_english_context_gives_the_same_headline_as_none():
    """Compatibility guard: with the English context the values equal those without a context (passes today)."""
    assert cls()().headline(F.run(), ctx=ctx()) == cls()().headline(F.run())


# ── The tool's Fail is not a verdict ────────────────────────────────────────

# ── Wording ─────────────────────────────────────────────────────────────────

def test_pass_and_fail_appear_only_as_the_tool_stated_them():
    html = render()
    t = text(soup(html))
    heads, rows = table_with(html, "Concern")
    stated = [r[-1] for r in rows if r[-1] in ("Pass", "Fail")]
    assert stated, "missing feature: Pass / Fail values in the group table"
    run_line = re.findall(r"All tolerance checks: (?:Pass|Fail)", t)
    # "Pass rate" (the column and the chart title) is LangBiTe's own measure, not a Pass / Fail value
    words = re.findall(r"\b(?:Pass|Fail)\b(?! rate)", t)
    assert len(words) == len(stated) + len(run_line) + 2   # + "Pass" and "Fail" of the column header
    low = t.lower()
    for w in ("verdict", "compliant", "unsafe", "better", "worse"):
        assert w not in low, w
    assert not re.search(r"\bsafe\b", low)


# ── English singular ────────────────────────────────────────────────────────

ONE = "Overall pass rate: {rate} across {groups} groups|one"


def test_en_json_holds_the_singular_form_only():
    path = PKG_DIR / "i18n" / "en.json"
    assert path.exists(), "missing feature: i18n/en.json"
    cat = json.loads(path.read_text(encoding="utf-8"))
    assert cat["_meta"]["code"] == "en"
    assert cat["messages"] == {ONE: "Overall pass rate: {rate} across {groups} group"}


def _english_package_ctx():
    i18n = need(f"{I}.i18n")
    cat = i18n.package_catalogue(P, "en")
    assert cat is not None, f"missing feature: {P}/i18n/en.json"
    t = i18n.translator(cat)
    return ctx(translate_for=lambda pkg: t)


def test_one_group_is_singular_four_are_plural():
    c = _english_package_ctx()
    one = text(soup(cls()().render(F.run([F.m("Overall Pass Rate", 0.6, ""), F.GROUPS[0]]), c)))
    assert re.search(r"across 1 group(?!s)", one), one[:300]
    four = text(soup(cls()().render(F.run(), c)))
    assert "across 4 groups" in four
