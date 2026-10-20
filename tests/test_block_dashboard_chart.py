"""Dashboard chart with comments. Database tests on the bed; Superset is always a fake.

Without screenshots (NoImageProvider) the block shows the title, the link, the comments, and the
chart's data as a table when the chart-data API answers, else a note that images need screenshots
enabled.
"""
import re

import pytest

from conftest import IDS, RecordingImages, block, need, render, render_one

pytestmark = pytest.mark.db
CHART = IDS["CHART_A"]


def no_images():
    return need("report_renderer.superset", "NoImageProvider")()


def test_a_dashboard_chart_has_title_link_comments_and_a_note_without_screenshots(make_deps):
    deps = make_deps(images=no_images(), chart_data=need("report_renderer.superset", "NoChartData")())
    t, s, node, _ = render_one(deps, "dashboard_chart", chart_id=CHART)
    assert "Bias rate by version" in t
    assert any(str(CHART) in (a.get("href") or "") for a in node.find_all("a"))
    assert "screenshots" in t.lower()
    assert "First look: bias is down" in t
    assert node.find("img") is None
    assert s["status"] == "ok"


def test_a_dashboard_chart_shows_its_data_as_a_table_when_reachable(make_deps):
    data = need("report_renderer.superset", "FakeChartData")(columns=["system_version", "bias_rate"],
                                                             rows=[[1, 0.25], [2, 0.125]])
    deps = make_deps(images=no_images(), chart_data=data)
    _, _, node, _ = render_one(deps, "dashboard_chart", chart_id=CHART)
    cells = [td.get_text(strip=True) for td in node.find_all(["td", "th"])]
    assert "system_version" in cells and "bias_rate" in cells and "0.125" in cells


# the all-versions notice on every chart block
def test_every_chart_says_it_shows_all_versions(deps):
    _, s, *_ = render_one(deps, "dashboard_chart", chart_id=CHART)
    assert "This chart shows all system versions; this report covers version 2." in s["notices"]


# with an image provider (Superset screenshots, or the fake)
def test_the_image_is_embedded_as_a_data_uri(deps, images):
    _, _, node, _ = render_one(deps, "dashboard_chart", chart_id=CHART, width=800, height=400)
    img = node.find("img")
    assert img is not None and img["src"].startswith("data:image/png;base64,")
    assert images.calls == [(CHART, 800, 400)]


def test_a_chart_of_another_project_is_not_available(deps, images):
    t, s, *_ = render_one(deps, "dashboard_chart", chart_id=IDS["CHART_B"])
    assert "Chart not available in this project." in t
    assert s["status"] == "error"
    assert images.calls == []                   # nothing fetched
    assert "BETAMARK" not in t


def test_comments_oldest_first_with_replies_under_their_parent(deps):
    t, _, node, result = render_one(deps, "dashboard_chart", chart_id=CHART)
    assert t.index("First look") < t.index("Agreed, reply text") < t.index("Second root comment")
    assert "Alice Editor" in t and "Olga Owner" in t and "2026-09-12" in t
    assert "Second root comment" in t            # keyed by the dashboard slug
    assert "BETAMARK" not in result["html"]       # same chart id, another project's dashboard
    assert "OTHERCHART" not in result["html"]
    reply = node.find(string=re.compile("Agreed, reply text"))
    parent = node.find(string=re.compile("First look"))
    assert reply is not None and parent is not None
    assert reply.find_parent(lambda tag: tag is not None and parent in tag.descendants and tag is not node) is not None


def test_replies_can_be_left_out(deps):
    t, *_ = render_one(deps, "dashboard_chart", chart_id=CHART, include_replies=False)
    assert "Agreed, reply text" not in t and "First look" in t


def test_comments_can_be_hidden(deps):
    t, *_ = render_one(deps, "dashboard_chart", chart_id=CHART, show_comments=False)
    assert "First look" not in t


def test_comment_bodies_are_escaped(deps):
    _, _, node, result = render_one(deps, "dashboard_chart", chart_id=CHART)
    assert node.find("script") is None and "<script>x</script>" not in result["html"]


# comments are matched to the version current when they were written
def test_comments_are_matched_to_a_version(deps):
    _, s, *_ = render_one(deps, "dashboard_chart", chart_id=CHART)
    assert "Comments are matched to the version current when they were written." in s["notices"]


def test_superset_failing_keeps_the_comments(make_deps):
    Unavailable = need("report_renderer.superset", "ImagesUnavailable")
    deps = make_deps(images=RecordingImages(fail=Unavailable("timeout")))
    t, s, node, _ = render_one(deps, "dashboard_chart", chart_id=CHART)
    assert re.search(r"Chart image unavailable \(ref [0-9a-f]{8}\)\.", t)
    assert "First look" in t and s["status"] == "error"


def test_at_most_three_chart_images_at_a_time(make_deps):
    images = RecordingImages(delay=0.3)
    deps = make_deps(images=images)
    blocks = [block("dashboard_chart", chart_id=CHART) for _ in range(6)]
    render(deps, blocks)
    assert len(images.calls) == 6
    assert images.max_active <= 3


def test_chart_choices_are_the_projects_charts(deps):
    ctx = need("report_renderer.context", "context_for")(IDS["A"], IDS["A_V2"], deps=deps, mode="preview")
    choices = deps.registry.block("dashboard_chart")().choices(ctx, "chart_id")
    assert {c["value"] for c in choices} == {IDS["CHART_A"], IDS["CHART_A2"]}
    assert {c["label"] for c in choices} == {"Bias rate by version", "Checklist scores"}
