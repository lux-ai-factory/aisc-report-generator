"""Charts the plugin declares (get_metric_visualizations), drawn in Test results. The snapshot
carries them per plugin configuration (the composer asks the platform); for now LangBiTe and Data Drift use
them. A bars chart is a bar per group (the mean score of its measures), a table a row per group."""
import pytest

from conftest import block, need, section, snapshot, soup, text, window

LANGBITE = [
    {"chart_type": "bars", "metrics": ["Bias Evaluation Results"], "title": "Pass rate per concern",
     "description": "Share of judged answers that passed, per concern.", "group_by_dimensions": ["concern"]},
    {"chart_type": "table", "metrics": ["Failed cases"], "title": "Failed cases",
     "group_by_dimensions": ["concern", "prompt", "response", "expected"]},
]
DRIFT = [
    {"chart_type": "bars", "metrics": ["Drift Score"], "title": "Drift Score"},
    {"chart_type": "bars", "metrics": ["psi"], "title": "PSI per feature", "group_by_dimensions": ["feature"]},
    {"chart_type": "table", "metrics": ["psi", "ks"], "title": "Statistics per feature",
     "group_by_dimensions": ["feature"]},
]


def m(name, score, **dims):
    return {"name": name, "metric": name, "score": score, "dimensions": dims or None}


LANGBITE_MS = [
    m("Bias Evaluation Results", 0.5, concern="sexism", language="en_us"),
    m("Bias Evaluation Results", 0.7, concern="sexism", language="fr_fr"),
    m("Bias Evaluation Results", 1.0, concern="racism", language="en_us"),
    m("Failed cases", 1.0, concern="sexism", prompt="Are women good at maths?", response="No", expected="yes"),
    m("Overall Pass Rate", 0.73),
]
DRIFT_MS = [m("Drift Score", 0.4), m("psi", 0.31, feature="income"), m("psi", 0.02, feature="age"),
            m("ks", 0.2, feature="income"), m("ks", 0.05, feature="age")]


def draw(charts, measurements):
    from report_renderer.declared import render_declared

    class Ctx:
        decimal_separator, percent_format, chart_colours = ".", "{value}%", None

        @staticmethod
        def t(msgid, **params):
            return msgid.format(**params)
    return soup(str(render_declared(charts, measurements, Ctx())))


def test_bars_are_the_mean_of_each_group():
    node = draw(LANGBITE[:1], LANGBITE_MS)
    svg = node.find("svg")
    assert svg is not None and "Pass rate per concern" in text(node)
    labels = [t.get_text() for t in svg.find_all("text")]
    assert "racism" in labels and "sexism" in labels
    assert "Share of judged answers that passed, per concern." in text(node)


def test_a_table_lists_each_group_and_leaves_out_a_value_that_says_nothing():
    node = draw(LANGBITE[1:], LANGBITE_MS)
    rows = [[text(td) for td in tr.find_all("td")] for tr in node.find_all("tr") if tr.find_all("td")]
    assert rows == [["sexism", "Are women good at maths?", "No", "yes"]]
    heads = [text(th) for th in node.find_all("th")]
    assert heads == ["concern", "prompt", "response", "expected"]


def test_a_table_keeps_a_score_column_with_one_row_or_equal_scores():
    """A table dropped any metric whose means were all the same, so a one-group table
    lost its only value column, and two groups scoring 0.5 lost both scores. Only the constant 1 that
    marks a listed case (LangBiTe's Failed cases) says nothing."""
    chart = [{"chart_type": "table", "metrics": ["pass_rate"], "title": "Pass rate",
              "group_by_dimensions": ["concern"]}]
    def table(ms):
        node = draw(chart, ms)
        return ([text(th) for th in node.find_all("th")],
                [[text(td) for td in tr.find_all("td")] for tr in node.find_all("tr") if tr.find_all("td")])
    assert table([m("pass_rate", 0.4, concern="gender")]) == (["concern", "pass_rate"], [["gender", "0.4"]])
    assert table([m("pass_rate", 0.5, concern="gender"), m("pass_rate", 0.5, concern="age")]) == (
        ["concern", "pass_rate"], [["age", "0.5"], ["gender", "0.5"]])


def test_data_drift_draws_its_three_declared_charts():
    node = draw(DRIFT, DRIFT_MS)
    assert len(node.find_all("svg")) == 2
    rows = [[text(td) for td in tr.find_all("td")] for tr in node.find_all("tr") if tr.find_all("td")]
    assert rows == [["age", "0.02", "0.05"], ["income", "0.31", "0.2"]]
    assert [text(th) for th in node.find_all("th")] == ["feature", "psi", "ks"]


def test_a_chart_with_no_measures_is_left_out():
    assert draw([{"chart_type": "bars", "metrics": ["absent"], "title": "Nothing"}], DRIFT_MS).find("svg") is None


def test_the_snapshot_may_carry_them_as_charts_per_configuration():
    from report_renderer.snapshot import validate

    s = snapshot([block("cover")])
    assert validate({**s, "declared_charts": {"2": LANGBITE}}) == []
    assert validate({**s, "declared_charts": ["not", "a", "map"]}) != []


# in the report, on the bed: Alpha v2's LangBiTe run (plugin configuration 2) has the measure bias_rate 0.125

BIAS = [{"chart_type": "bars", "metrics": ["bias_rate"], "title": "Bias rate declared"}]


@pytest.mark.db
def test_test_results_draws_langbites_declared_charts(deps):
    b = block("test_results")
    s = snapshot([b], selection=window("2026-09-10T09:00", "2026-09-10T09:01"))
    s["declared_charts"] = {"2": BIAS, "3": [{"chart_type": "bars", "metrics": ["mystery_metric"],
                                              "title": "Mystery declared"}]}
    node = section(need("report_renderer.document", "render")(s, deps)["html"], b["instance_id"])
    assert "Bias rate declared" in text(node)
    assert "Mystery declared" not in text(node)          # only LangBiTe and Data Drift, for now


@pytest.mark.db
def test_without_declared_charts_test_results_is_as_before(deps):
    b = block("test_results")
    s = snapshot([b], selection=window("2026-09-10T09:00", "2026-09-10T09:01"))
    node = section(need("report_renderer.document", "render")(s, deps)["html"], b["instance_id"])
    assert "Bias rate declared" not in text(node) and "LangBiTe" in text(node)


@pytest.mark.db
def test_a_word_report_takes_the_declared_charts_too(deps):
    """Already passing when written: the Word export takes the charts and tables tool sections already use."""
    b = block("test_results")
    s = snapshot([b], mode="docx", selection=window("2026-09-10T09:00", "2026-09-10T09:01"))
    s["declared_charts"] = {"2": BIAS + [{"chart_type": "table", "metrics": ["bias_rate"], "title": "Bias table"}]}
    out = need("report_renderer.document", "render")(s, deps)
    assert out.get("docx_base64")


def test_a_percent_chart_shows_its_ratios_as_percent():
    """A pass rate is a ratio from 0 to 1: a concern that passed read "1". A chart that
    says value_format "percent" shows 100%, in bars and in tables."""
    bars = draw([{**LANGBITE[0], "value_format": "percent"}], LANGBITE_MS)
    labels = [t.get_text() for t in bars.find("svg").find_all("text")]
    assert "100%" in labels and "60%" in labels
    table = draw([{"chart_type": "table", "metrics": ["Bias Evaluation Results"], "value_format": "percent",
                   "group_by_dimensions": ["concern"]}], LANGBITE_MS)
    rows = [[text(td) for td in tr.find_all("td")] for tr in table.find_all("tr") if tr.find_all("td")]
    assert rows == [["racism", "100%"], ["sexism", "60%"]]


def test_a_chart_without_a_format_shows_plain_numbers():
    labels = [t.get_text() for t in draw(LANGBITE[:1], LANGBITE_MS).find("svg").find_all("text")]
    assert "1" in labels and "100%" not in labels
