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


def test_two_blocks_with_the_same_title_stay_two_subsections():
    node = render([plot(1, "Results", "By register"), plot(2, "Results", "By category")])
    blocks = node.select(".export-block")
    assert [b.find("h3").get_text(strip=True) for b in blocks] == ["Results", "Results"]
    assert [[h.get_text(strip=True) for h in b.find_all("h4")] for b in blocks] == [["By register"], ["By category"]]


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


def render_with(rows, options):
    ctx = SimpleNamespace(t=lambda text, **kw: text.format(**kw))
    result = SupersetExportsBlock().render({"exports": rows}, {"dashboards": "all", **options}, ctx)
    return BeautifulSoup(result.html, "html.parser")


def block_comments(node):
    return [(b.find(class_="export-block-comment").get_text(" ", strip=True)
             if b.find(class_="export-block-comment") else None) for b in node.select(".export-block")]


def test_each_block_prints_its_own_comment_under_its_heading():
    node = render_with([plot(1, "LangBiTe (Mijke)", "By register"), plot(2, "StrongREJECT (Mijke)", "By category")],
                       {"comments": {"2": "Refusals held in every language."}})
    assert block_comments(node) == [None, "Refusals held in every language."]
    second = node.select(".export-block")[1]
    assert second.find("h3").find_next_sibling() is second.find(class_="export-block-comment")


def test_a_block_comment_is_escaped_and_keeps_its_line_breaks():
    node = render_with([plot(1, "LangBiTe (Mijke)", "By register")],
                       {"comments": {"1": "First <b>line</b>\nsecond line\n\nNew paragraph"}})
    comment = node.select_one(".export-block-comment")
    assert comment.find("b") is None and "<b>line</b>" in comment.get_text()
    assert [p.decode_contents() for p in comment.find_all("p")] == [
        "First &lt;b&gt;line&lt;/b&gt;<br/>second line", "New paragraph"]


def test_an_empty_or_unwritten_block_comment_prints_nothing():
    rows = [plot(1, "A", "x"), plot(2, "B", "y"), plot(3, "C", "z")]
    node = render_with(rows, {"comments": {"1": "", "2": "  \n ", "3": "Write this section."}})
    assert block_comments(node) == [None, None, None]


def test_a_layout_without_comments_renders_as_before():
    rows = [plot(1, "A", "x"), plot(2, "B", "y")]
    assert str(render_with(rows, {})) == str(render(rows))
    assert block_comments(render(rows)) == [None, None]


def test_a_comment_for_a_block_not_shown_is_left_out():
    node = render_with([plot(1, "A", "x"), plot(2, "B", "y")], {"dashboards": ["1"], "comments": {"2": "Hidden"}})
    assert "Hidden" not in node.get_text()


def test_the_comments_option_holds_one_text_per_block_and_defaults_to_none():
    cls = SupersetExportsBlock
    assert cls.full_default_options()["comments"] == {}
    assert cls.options_problems({**cls.full_default_options(), "comments": {"7": "Text"}}) == []
    assert cls.options_problems({**cls.full_default_options(), "comments": {"7": 3}})
    prop = cls.full_options_schema()["properties"]["comments"]
    assert prop["additionalProperties"]["x-aisc-prose"] is True
    assert prop["x-aisc-per-choice-of"] == "dashboards"          # one box per block the composer offers
    assert cls.contract_version == 1                              # an optional option with a default: same contract
