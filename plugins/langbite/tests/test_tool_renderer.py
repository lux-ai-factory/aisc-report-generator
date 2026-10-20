"""LANGBITEToolRenderer: the LangBiTe section of Test results. No verdict of the report's own: LangBiTe's
tolerance check is shown as the tool's result."""
import re

import fixtures as F
from conftest import I, charts_in, ctx, need, soup, table_with, text

P = "aisc_report_plugin_langbite"


def cls():
    return need(P, "LANGBITEToolRenderer")


def render(run=None, **opts):
    return cls()().render(run or F.run(), ctx(**opts))


# ── Declaration ─────────────────────────────────────────────────────────────

def test_declaration():
    c = cls()
    assert issubclass(c, need(I, "BaseToolRenderer"))
    assert c.tool_names == ("LangBiTe",)
    assert c.contract_version == 2
    assert c.chart_ids == {"pass_rate_by_concern": "Pass rate by concern"}


def test_matches_the_live_plugin_row_only():
    c = cls()
    assert c.matches(F.TOOL)
    assert c.matches({"display_name": "LangBiTe", "name": "LangBiTeEvaluationPlugin",
                      "package_name": "aisc-plugin-langbite"})
    assert not c.matches(F.STRONGREJECT)


# ── Summary line ────────────────────────────────────────────────────────────

def test_summary_line():
    t = text(soup(render()))
    assert re.search(r"Overall pass rate: (68(\.\d+)?|69)\s?% across 4 groups", t), t[:400]
    assert "Run: finished" in t


def test_failed_run_says_why():
    ms = [F.m("LangBiTe Run Success", 0.0, "LangBiTe failed: timeout after 600 s"),
          F.m("Overall Pass Rate", 0.0, "LangBiTe failed: timeout after 600 s"),
          F.m("All Tolerances Passed", 0.0, "0/0 tolerance checks passed")]
    t = text(soup(render(F.run(ms))))
    assert "Run: failed (LangBiTe failed: timeout after 600 s)" in t


# ── One row per group ───────────────────────────────────────────────────────

def test_group_table_columns():
    heads, rows = table_with(render(), "Concern")
    assert heads is not None, "no group table"
    expected = ["Concern", "Model", "Language", "Input type", "Reflection type", "Passed", "Failed", "Pass rate",
                "Tolerance set in LangBiTe", "Pass / Fail (LangBiTe tolerance check)"]
    assert len(heads) == len(expected)
    for h, e in zip(heads, expected):
        assert h.startswith(e), (h, e)


def test_group_rows_ordered_by_concern_model_language():
    _, rows = table_with(render(), "Concern")
    assert [(r[0], r[2]) for r in rows] == [("ageism", "en_us"), ("gender", "en_us"), ("gender", "fr_fr"),
                                             ("religion", "en_us")]


def test_group_cells():
    _, rows = table_with(render(), "Concern")
    gender_en = rows[1]
    assert gender_en[1] == "gpt-4o-mini" and gender_en[3] == "prompt" and gender_en[4] == "observational"
    assert gender_en[5] == "9 of 10" and gender_en[6] == "1 of 10"
    assert re.fullmatch(r"90(\.0+)?\s?%?", gender_en[7])
    assert re.fullmatch(r"80(\.0+)?\s?%?", gender_en[8])
    assert gender_en[9] == "Pass"
    assert rows[2][9] == "Fail" and rows[3][9] == "Not evaluated"
    assert rows[3][5] == "1 of 2"


# ── Chart ───────────────────────────────────────────────────────────────────

def test_chart_of_pass_rate_by_concern():
    svgs = charts_in(render(show_charts=True))
    assert len(svgs) == 1
    assert svgs[0]["aria-label"] == "Pass rate by concern"


def test_no_chart_when_show_charts_is_off():
    html = render(show_charts=False)
    assert charts_in(html) == []
    assert table_with(html, "Concern")[0] is not None


def test_charts_returns_the_spec_drawn():
    specs = cls()().charts(F.run())
    assert [s["id"] for s in specs] == ["pass_rate_by_concern"]
    s = specs[0]
    assert s["kind"] == "hbar" and s["value_format"] == "percent"
    assert s.get("axis_min", 0) == 0 and s["axis_max"] == 1
    assert [x["label"] for x in s["series"]] == ["ageism", "gender", "religion"]
    assert [round(x["value"], 4) for x in s["series"]] == [0.75, 0.75, 0.5]   # gender = mean(0.9, 0.6)


def test_chart_is_drawn_with_charts_svg():
    spec = cls()().charts(F.run())[0]
    svg = need(f"{I}.charts", "svg")(spec, {"primary": "#000FDF", "text": "#000000", "grid": "#CCCCCC"})
    assert 'aria-label="Pass rate by concern"' in str(svg)


# ── No verdict ──────────────────────────────────────────────────────────────

def test_verdict_is_none():
    assert cls()().verdict(F.run()) is None


def test_no_verdict_words_of_the_report():
    t = text(soup(render())).lower()
    assert "verdict" not in t
    assert "tolerance set in langbite" in t and "pass / fail (langbite tolerance check)" in t


# ── Robustness ──────────────────────────────────────────────────────────────

def test_unparsable_description_gives_n_a_and_score_pass_rate():
    ms = F.SUMMARY + [F.m("hate | gpt-4o-mini | en_us | prompt | observational", 0.42, "garbage")]
    _, rows = table_with(render(F.run(ms)), "Concern")
    row = [r for r in rows if r[0] == "hate"][0]
    assert row[5] == row[6] == row[8] == row[9] == "n/a"
    assert re.fullmatch(r"42(\.0+)?\s?%?", row[7])


def test_unknown_measurements_are_listed_never_dropped():
    ms = F.SUMMARY + F.GROUPS + [F.m("Custom metric", 0.3, "x"), F.m("a | b | c | d", 0.2, "four parts only")]
    html = render(F.run(ms))
    t = text(soup(html))
    assert "Other measurements" in t
    assert "Custom metric" in t and "a | b | c | d" in t
    _, rows = table_with(html, "Concern")
    assert len(rows) == 4


# ── Headline ────────────────────────────────────────────────────────────────

def test_headline():
    items = cls()().headline(F.run())
    assert 1 <= len(items) <= 4
    assert all(isinstance(i["label"], str) and isinstance(i["value"], str) for i in items)
    by = {i["label"]: i["value"] for i in items}
    assert list(by) == ["Overall pass rate", "Tolerance checks passed", "Groups"]
    assert re.fullmatch(r"(68(\.\d+)?|69)\s?%", by["Overall pass rate"])
    assert by["Tolerance checks passed"] == "1 of 4"
    assert by["Groups"] == "4"


# ── Detail = summary ────────────────────────────────────────────────────────

def test_summary_detail_shows_line_and_chart_only():
    html = render(detail="summary")
    assert "Overall pass rate" in text(soup(html))
    assert "All tolerance checks: Fail (1 of 4 passed)" in text(soup(html))
    assert len(charts_in(html)) == 1
    assert table_with(html, "Concern")[0] is None


# ── Options come from ctx.tool_options only ─────────────────────────────────

def test_a_context_without_tool_options_still_renders():
    from types import SimpleNamespace

    html = cls()().render(F.run(), SimpleNamespace(language="en", t=lambda s, **k: s,
                                                    translate_for=lambda p: (lambda s, **k: s)))
    assert "Overall pass rate" in html


# ── Artifacts and escaping ──────────────────────────────────────────────────

def test_artifact_contents_are_never_printed():
    html = render(F.run(artifacts=[{"name": "langbite-report.csv", "file_size": 2048,
                                    "data": "HARMFULPROMPTCONTENT"}]))
    assert "HARMFULPROMPTCONTENT" not in html


def test_values_are_escaped():
    ms = F.SUMMARY + [F.g("gender", "<script>alert(1)</script>", "en_us", 0.5, "Passed", "0.8", 1, 1, 2)]
    html = render(F.run(ms))
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


# ── Headline values ─────────────────────────────────────────────────────────

def test_headline_without_a_context_stays_english():
    by = {i["label"]: i["value"] for i in cls()().headline(F.run())}
    assert by["Tolerance checks passed"] == "1 of 4"
