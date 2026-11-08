"""Exported results drawn from saved plots handed in directly. No database."""
from datetime import datetime
from types import SimpleNamespace

from bs4 import BeautifulSoup

from report_renderer.blocks.superset_exports import SupersetExportsBlock

SVG = b'<svg width="10" height="10" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'


def plot(dashboard_id, title, chart):
    return {"dashboard_id": dashboard_id, "dashboard_title": title, "chart": chart, "tags": [], "comment": "",
            "author_name": "Alice", "created_at": datetime(2026, 2, 1), "svg": SVG}


def render(rows):
    ctx = SimpleNamespace(t=lambda text, **kw: text.format(**kw))
    result = SupersetExportsBlock().render({"exports": rows}, {"dashboards": "all"}, ctx)
    return BeautifulSoup(result.html, "html.parser")


def parts(rows, **options):
    ctx = SimpleNamespace(t=lambda text, **kw: text.format(**kw))
    return SupersetExportsBlock().render({"exports": rows}, {"dashboards": "all", **options}, ctx).parts


def test_each_tool_is_a_part_titled_with_its_name_even_with_the_same_title():
    got = parts([plot(1, "Results", "By register"), plot(2, "Results", "By category")])
    assert [p["title"] for p in got] == ["Results", "Results"]
    assert [[h.get_text(strip=True) for h in BeautifulSoup(p["html"], "html.parser").find_all("h4")] for p in got] == [
        ["By register"], ["By category"]]
    assert all(BeautifulSoup(p["html"], "html.parser").find("h3") is None for p in got)   # the section heading is the title


def test_the_whole_block_html_is_its_parts_one_after_another():
    ctx = SimpleNamespace(t=lambda text, **kw: text.format(**kw))
    result = SupersetExportsBlock().render({"exports": [plot(1, "A", "x"), plot(2, "B", "y")]}, {"dashboards": "all"},
                                           ctx)
    assert result.status == "ok" and str(result.html) == "".join(str(p["html"]) for p in result.parts)


def test_nothing_saved_has_no_parts():
    ctx = SimpleNamespace(t=lambda text, **kw: text.format(**kw))
    result = SupersetExportsBlock().render({"exports": []}, {"dashboards": "all"}, ctx)
    assert result.status == "empty" and getattr(result, "parts", None) in (None, [])


def test_the_block_says_its_plots_are_as_saved_whatever_version_or_period():
    text = render([plot(1, "Results", "By register")]).get_text(" ", strip=True)
    assert "Plots as saved on the dashboards, whatever version or period they show." in text


def rows_lines(node):
    return [(p.find(class_="export-rows").get_text(strip=True) if p.find(class_="export-rows") else None)
            for p in node.select(".export-plot")]


def render_in_english(rows):
    from report_renderer import languages

    ctx = SimpleNamespace(t=languages.translator()[0])
    return BeautifulSoup(SupersetExportsBlock().render({"exports": rows}, {"dashboards": "all"}, ctx).html, "html.parser")


def test_each_plot_says_the_rows_its_chart_drew_when_it_was_saved():
    node = render_in_english([{**plot(1, "Results", "A"), "rows": 2}, {**plot(1, "Results", "B"), "rows": 1},
                              {**plot(1, "Results", "C"), "rows": 0}])
    assert rows_lines(node) == ["2 rows", "1 row", "0 rows"]
    first = node.select(".export-plot")[0]
    assert first.find("img").find_next(class_="export-rows") is first.find(class_="export-rows")   # under the plot


def test_a_plot_saved_without_a_count_shows_none():
    node = render_in_english([{**plot(1, "Results", "A"), "rows": None}, plot(1, "Results", "B")])
    assert rows_lines(node) == [None, None]


def test_each_tool_part_carries_its_own_commentary_text():
    got = parts([plot(1, "LangBiTe (Mijke)", "By register"), plot(2, "StrongREJECT (Mijke)", "By category")],
                comments={"2": "Refusals held in every language."})
    assert [p["commentary"] for p in got] == [None, "Refusals held in every language."]


def test_a_comment_for_a_tool_not_shown_is_left_out():
    got = parts([plot(1, "A", "x"), plot(2, "B", "y")], dashboards=["1"], comments={"2": "Hidden"})
    assert [p["title"] for p in got] == ["A"] and "Hidden" not in str(got)


def test_the_plots_note_is_printed_once_in_the_first_tool():
    got = parts([plot(1, "A", "x"), plot(2, "B", "y")])
    note = "Plots as saved on the dashboards, whatever version or period they show."
    assert [note in str(p["html"]) for p in got] == [True, False]


def test_the_comments_option_holds_one_text_per_block_and_defaults_to_none():
    cls = SupersetExportsBlock
    assert cls.full_default_options()["comments"] == {}
    assert cls.options_problems({**cls.full_default_options(), "comments": {"7": "Text"}}) == []
    assert cls.options_problems({**cls.full_default_options(), "comments": {"7": 3}})
    prop = cls.full_options_schema()["properties"]["comments"]
    assert prop["additionalProperties"]["x-aisc-prose"] is True
    assert prop["x-aisc-per-choice-of"] == "dashboards"          # one box per tool the composer offers
    assert prop["title"] == "Commentary per tool"
    # each chosen tool is a section of its own: the composer numbers them and checks every tool for "all"
    assert cls.full_options_schema()["properties"]["dashboards"]["x-aisc-section-per-choice"] is True
    assert cls.contract_version == 1                              # an optional option with a default: same contract
