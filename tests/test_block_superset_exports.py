"""Exported results: one subsection per Superset block; in it, one saved plot after another: its filters as text tags,
the plot as the vector file saved from Superset, the comment. Nothing is drawn here."""
import base64

import pytest

from conftest import IDS, need, render_one

pytestmark = pytest.mark.db


def plots(node):
    return node.find_all("div", class_="export-plot")


def test_each_block_is_a_subsection_with_its_plots_one_after_another(deps):
    _, status, node, _ = render_one(deps, "superset_exports")
    assert status["status"] == "ok"
    assert [h.get_text(strip=True) for h in node.select(".export-block > h3")] == ["Alpha results"]
    assert len(plots(node)) == 3


def test_the_plot_is_the_saved_vector_file_itself(deps):
    _, _, node, _ = render_one(deps, "superset_exports")
    sources = [i["src"] for i in node.find_all("img")]
    assert all(s.startswith("data:image/svg+xml;base64,") for s in sources)
    assert any(b"new" in base64.b64decode(s.split(",", 1)[1]) for s in sources)


def test_the_filters_are_text_tags_above_the_plot(deps):
    _, _, node, _ = render_one(deps, "superset_exports")
    first = plots(node)[0]
    tags = first.find(class_="export-tags")
    assert [t.get_text(strip=True) for t in tags.find_all(class_="tag")] == ["Model: OpenAI"]
    assert tags.find_next("img") is first.find("img")


def test_the_same_plot_with_other_filters_is_another_plot(deps):
    text, _, node, _ = render_one(deps, "superset_exports")
    assert "Model: OpenAI" in text and "Model: Local" in text


def test_saving_again_with_the_same_filters_replaces_the_plot(deps):
    text, *_ = render_one(deps, "superset_exports")
    assert "Newest comment" in text and "older comment" not in text


def test_plots_stay_in_the_order_they_were_saved(deps):
    _, _, node, _ = render_one(deps, "superset_exports")
    assert [p.find("h4").get_text(strip=True) for p in plots(node)] == ["By register", "By register", "By category"]


def test_nothing_of_another_project_is_shown(deps):
    text, *_ = render_one(deps, "superset_exports")
    assert "another project" not in text


def test_who_saved_it_and_when(deps):
    text, *_ = render_one(deps, "superset_exports")
    assert "Alice" in text and "2026-02-01" in text


def test_nothing_is_drawn_here(deps):
    _, _, node, _ = render_one(deps, "superset_exports")
    assert node.find("svg") is None


def test_a_project_with_nothing_saved_says_how_to_save(deps):
    text, status, *_ = render_one(deps, "superset_exports", project="C", system="C_V1")
    assert status["status"] == "empty" and "Save to report" in text


def test_the_blocks_can_be_chosen(deps):
    ctx = need("report_renderer.context", "context_for")(IDS["A"], IDS["A_V2"], deps=deps, mode="preview")
    choices = deps.registry.block("superset_exports")().choices(ctx, "dashboards")
    _, status, *_ = render_one(deps, "superset_exports", dashboards=[str(choices[0]["value"])])
    assert status["status"] == "ok"
    _, status, *_ = render_one(deps, "superset_exports", dashboards=["no such block"])
    assert status["status"] == "empty"


def test_a_plot_is_never_split_from_its_title_and_tags(deps):
    _, _, node, _ = render_one(deps, "superset_exports")
    assert all("break-inside:avoid" in p.get("style", "").replace(" ", "") for p in plots(node))


def test_each_plot_says_the_rows_its_chart_drew_when_it_was_saved(deps):
    """The seed: the newest OpenAI plot was saved with 2 rows, the Local one with 1, By category without a count."""
    _, _, node, _ = render_one(deps, "superset_exports")
    assert [(p.find(class_="export-rows").get_text(strip=True) if p.find(class_="export-rows") else None)
            for p in plots(node)] == ["2 rows", "1 row", None]


def test_a_dashboard_database_made_before_the_rows_column_reads_no_count_and_no_error(bed):
    """An install whose dashboard has not started since the column was added: aisc_report_plot has no rows."""
    import dataclasses

    from conftest import bed_sources
    from report_renderer.data import superset_db

    old = "superset_before_rows"
    bed.psql("postgres", f"DROP DATABASE IF EXISTS {old}")
    bed.psql("postgres", f"CREATE DATABASE {old} TEMPLATE superset")
    try:
        bed.psql(old, "ALTER TABLE aisc_report_plot DROP COLUMN rows")
        older = dataclasses.replace(bed_sources(bed), superset_dsn=bed.dsn("report_ro", old))
        got = superset_db.exports(IDS["A"], IDS["A_V2"], sources=older)
        assert len(got) == 3 and [g["rows"] for g in got] == [None, None, None]
    finally:
        bed.psql("postgres", f"DROP DATABASE IF EXISTS {old}")
