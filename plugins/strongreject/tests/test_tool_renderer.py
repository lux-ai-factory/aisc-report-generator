"""STRONGREJECTToolRenderer: the StrongREJECT section of Test results.

The plugin writes 0.0 when it fails, which would read as "perfectly safe": such values are shown as
"not scored: {description}". No verdict, no colour bands (thresholds are out of scope)."""
import re

import fixtures as F
from conftest import I, charts_in, ctx, need, soup, table_with, text

P = "aisc_report_plugin_strongreject"


def cls():
    return need(P, "STRONGREJECTToolRenderer")


def render(run=None, **opts):
    return cls()().render(run or F.run(), ctx(**opts))


def test_declaration():
    c = cls()
    assert issubclass(c, need(I, "BaseToolRenderer"))
    assert c.tool_names == ("StrongREJECT",)
    assert c.contract_version == 2
    assert c.chart_ids == {"harmfulness_by_jailbreak": "Harmfulness by jailbreak"}


def test_matches_the_live_plugin_row_only():
    assert cls().matches(F.TOOL)
    assert not cls().matches(F.LANGBITE)


def test_key_numbers_state_their_direction():
    t = text(soup(render()))
    for label in ("Harmfulness (mean, 0 to 1, lower is safer)",
                  "Jailbreak resistance (1 minus harmfulness, higher is safer)",
                  "Baseline harmfulness, no jailbreak", "Worst jailbreak: pair"):
        assert label in t, label
    for value in ("0.2", "0.8", "0.05", "0.45"):
        assert value in t, value


def test_jailbreak_table():
    heads, rows = table_with(render(), "Jailbreak")
    assert heads is not None
    assert [h.split(" (")[0] for h in heads] == ["Jailbreak", "Harmfulness", "Prompts"]
    assert rows == [["none", "0.050", "20"], ["aim", "0.100", "20"], ["base64", "0.200", "20"],
                    ["pair", "0.450", "20"]]


def test_chart_of_harmfulness_by_jailbreak():
    svgs = charts_in(render(show_charts=True))
    assert len(svgs) == 1 and svgs[0]["aria-label"] == "Harmfulness by jailbreak"


def test_no_chart_when_show_charts_is_off():
    assert charts_in(render(show_charts=False)) == []


def test_chart_spec_has_a_fixed_0_to_1_axis():
    specs = cls()().charts(F.run())
    assert [s["id"] for s in specs] == ["harmfulness_by_jailbreak"]
    s = specs[0]
    assert s["value_format"] == "number" and s.get("axis_min", 0) == 0 and s["axis_max"] == 1
    assert {x["label"]: x["value"] for x in s["series"]} == {"none": 0.05, "aim": 0.1, "base64": 0.2, "pair": 0.45}


def test_a_failed_run_is_not_scored():
    html = render(F.failed_run())
    t = text(soup(html))
    assert "StrongREJECT did not produce scores in this run." in t
    for d in ("No score produced", "Not measured", "No attacked jailbreaks", "No 'none' baseline run"):
        assert f"not scored: {d}" in t, d
    assert "0.000" not in t and not re.search(r"\b0\.0\b", t)


def test_not_scored_values_are_excluded_from_charts_and_headline():
    r = F.failed_run()
    assert charts_in(render(r, show_charts=True)) == []
    assert cls()().headline(r) == []
    assert all(not s.get("series") for s in cls()().charts(r))


def test_one_not_scored_summary_leaves_the_others():
    ms = [F.m("StrongREJECT Harmfulness", 0.2, F.OK_HARM), F.m("Jailbreak Resistance", 0.8, F.OK_RES),
          F.m("Worst-Case Jailbreak Harmfulness", 0.0, "No attacked jailbreaks"),
          F.m("Baseline Harmfulness (no jailbreak)", 0.05, F.OK_BASE), F.jb("none", 0.05)]
    items = cls()().headline(F.run(ms))
    labels = " ".join(i["label"] for i in items).lower()
    assert "harmfulness" in labels and "resistance" in labels and "worst" not in labels
    assert "not scored: No attacked jailbreaks" in text(soup(render(F.run(ms))))


def test_success_text_is_compared_after_trimming():
    ms = [F.m("StrongREJECT Harmfulness", 0.2, "  " + F.OK_HARM + "  ")]
    t = text(soup(render(F.run(ms))))
    assert "not scored" not in t and "0.2" in t


def test_headline_when_scored():
    items = cls()().headline(F.run())
    assert 1 <= len(items) <= 4
    assert all(isinstance(i["label"], str) and isinstance(i["value"], str) for i in items)
    joined = " ".join(f"{i['label']} {i['value']}" for i in items)
    assert "0.2" in joined and "0.8" in joined and "pair" in joined


def test_verdict_is_none_and_no_colour_bands():
    assert cls()().verdict(F.run()) is None and cls()().verdict(F.failed_run()) is None
    html = render().lower()
    assert not re.search(r"\b(green|amber|red)\b", html)
    for colour in ("#ff0000", "#00ff00", "#ffa500", "#f00", "#0f0"):
        assert colour not in html


def test_artifact_contents_are_never_printed():
    html = render(F.run(artifacts=[{"name": "strongreject_per_prompt.csv", "file_size": 4096,
                                    "data": "HARMFULPROMPTCONTENT"}]))
    assert "HARMFULPROMPTCONTENT" not in html


def test_values_are_escaped():
    html = render(F.run(F.SCORED + [F.jb("<b>x</b>", 0.3)]))
    assert "<b>x</b>" not in html and "&lt;b&gt;" in html
