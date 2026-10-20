"""PROMPTFOOToolRenderer: the promptfoo section of Test results."""
import re

import fixtures as F
from conftest import I, charts_in, ctx, need, soup, text

P = "aisc_report_plugin_promptfoo"


def cls():
    return need(P, "PROMPTFOOToolRenderer")


def render(run=None, **opts):
    return cls()().render(run or F.run(), ctx(**opts))


def rows(html):
    """label cell -> value cell of the promptfoo table."""
    out = {}
    for tr in soup(html).find_all("tr"):
        cells = [text(c) for c in tr.find_all(["th", "td"])]
        if len(cells) >= 2:
            out[cells[0]] = " ".join(cells[1:])
    return out


def row(html, label):
    for k, v in rows(html).items():
        if k.startswith(label):
            return k, v
    raise AssertionError(f"no row {label!r} in {list(rows(html))}")


def named(html, label):
    """The row labelled exactly `label`, optionally followed by the unit's direction words in brackets."""
    for k, v in rows(html).items():
        if k == label or k.startswith(label + " ("):
            return k, v
    raise AssertionError(f"no row labelled {label!r} in {list(rows(html))}")


def test_declaration():
    c = cls()
    assert issubclass(c, need(I, "BaseToolRenderer"))
    assert c.tool_names == ("Promptfoo", "promptfoo")
    assert c.contract_version == 2
    assert c.chart_ids == {"rates": "Pass, fail and refusal rates"}


def test_matches_its_plugin_row_only():
    assert cls().matches(F.TOOL)
    assert not cls().matches(F.LANGBITE)


def test_table_of_the_six_measurements():
    html = render()
    assert row(html, "Tests run")[1] == "40"
    assert re.fullmatch(r"85(\.0+)?\s?%", named(html, "Pass")[1])
    assert re.fullmatch(r"15(\.0+)?\s?%", named(html, "Fail")[1])
    assert re.search(r"10(\.0+)?\s?%", row(html, "Refusal rate")[1])
    assert re.fullmatch(r"812\s?(ms)?", row(html, "Mean latency")[1])
    assert re.fullmatch(r"(USD\s?)?0\.0123(\s?USD)?", row(html, "Total cost")[1])


def test_direction_words_come_from_the_unit():
    html = render()
    assert named(html, "Pass")[0] == "Pass (higher is better)"
    assert named(html, "Fail")[0] == "Fail (lower is better)"
    for label in ("Mean latency", "Total cost"):
        assert "lower is better" in row(html, label)[0], label
    k, _ = row(html, "Refusal rate")
    assert "better" not in k


def test_refusal_rate_note():
    assert "estimated from the grader's reasons" in text(soup(render()))


def test_absent_rates_are_not_reported():
    html = render(F.run(F.LATENCY_COST_TESTS, number=3))
    for label in ("Pass", "Fail", "Refusal rate"):
        assert "not reported" in named(html, label)[1], label
    assert row(html, "Tests run")[1] == "12"


def test_chart_of_the_rates_present():
    svgs = charts_in(render(show_charts=True))
    assert len(svgs) == 1 and svgs[0]["aria-label"] == "Pass, fail and refusal rates"
    s = cls()().charts(F.run())[0]
    assert s["id"] == "rates" and s["value_format"] == "percent" and s.get("axis_min", 0) == 0 and s["axis_max"] == 1
    assert [x["label"] for x in s["series"]] == ["Pass", "Fail", "Refusal rate"]


def test_no_chart_when_show_charts_is_off_or_no_rate():
    assert charts_in(render(show_charts=False)) == []
    assert charts_in(render(F.run(F.LATENCY_COST_TESTS, number=3), show_charts=True)) == []


def test_a_run_without_measurements():
    t = text(soup(render(F.run([], status="Failed", artifacts=[], number=5))))
    assert "promptfoo wrote no results for this run." in t


def test_headline():
    items = cls()().headline(F.run())
    assert all(isinstance(i["label"], str) and isinstance(i["value"], str) for i in items)
    by = {i["label"]: i["value"] for i in items}
    assert re.fullmatch(r"85(\.0+)?\s?%", by["Pass"])
    assert by["Tests run"] == "40"
    assert len(items) <= 4


def test_verdict_is_none():
    assert cls()().verdict(F.run()) is None


def test_artifact_contents_are_never_printed():
    html = render(F.run(artifacts=[{"name": "promptfoo_results.json", "file_size": 8192,
                                    "data": "HARMFULPROMPTCONTENT"}]))
    assert "HARMFULPROMPTCONTENT" not in html


def test_units_are_escaped():
    ms = F.FULL[:-1] + [F.m("n_tests", 3.0, "<i>count</i>", "x")]
    assert "<i>count</i>" not in render(F.run(ms))
