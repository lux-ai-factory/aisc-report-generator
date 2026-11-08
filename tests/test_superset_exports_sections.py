"""Exported results in a document: one numbered section per tool (per results dashboard block with saved plots),
titled with the tool's name, in the table of contents and in the numbering, each with its own commentary.

The bed's project A has one dashboard with saved plots ("Alpha results"); these tests render on a copy of the
dashboard database that adds a second one with a plot ("StrongREJECT (Mijke)") and a third without any.
"""
import dataclasses

import pytest

from conftest import IDS, bed_sources, soup, status_of, text
from v2_core_helpers import blk, docx_all_text, docx_of, do_render, pdf_pages, snap

pytestmark = pytest.mark.db

TWO_TOOLS = "superset_two_tools"
SVG = "convert_to('<svg xmlns=\"http://www.w3.org/2000/svg\"><text>sr</text></svg>','UTF8')"


@pytest.fixture(scope="module")
def two_tools(bed):
    bed.psql("postgres", f"DROP DATABASE IF EXISTS {TWO_TOOLS}")
    bed.psql("postgres", f"CREATE DATABASE {TWO_TOOLS} TEMPLATE superset")
    bed.psql(TWO_TOOLS, "SET session_replication_role = replica;"
             " INSERT INTO dashboards (id, dashboard_title, slug, published, uuid) VALUES"
             " (11, 'StrongREJECT (Mijke)', 'sr', true, gen_random_uuid()),"
             " (12, 'Zeta nothing saved', 'zeta', true, gen_random_uuid());"
             " INSERT INTO dashboard_roles (id, role_id, dashboard_id) VALUES (11, 1, 11), (12, 1, 12);"
             " INSERT INTO aisc_report_plot (dashboard_id, chart, tab, tags, svg, sha256, comment, author_name,"
             f" created_at, rows) VALUES (11, 'Refusals', '', '[]', {SVG}, 'sr', '', 'Bob', '2026-02-05 10:00', 4);")
    yield dataclasses.replace(bed_sources(bed), superset_dsn=bed.dsn("report_ro", TWO_TOOLS))
    bed.psql("postgres", f"DROP DATABASE IF EXISTS {TWO_TOOLS}")


@pytest.fixture
def tdeps(make_deps, two_tools):
    return make_deps(sources=two_tools)


def tool_sections(html):
    return soup(html).select("section.block-superset_exports")


def headings(html):
    return [text(s.find("h2")) for s in tool_sections(html)]


def chapter_layout(exports, after=None, numbering=True, toc="on", mode="preview"):
    cover, ch = blk("cover"), blk("chapter", title="Tests")
    rest = [after] if after else []
    return snap([cover, blk("free_text", title="Intro", text="Body."), ch, exports, *rest], mode=mode,
                document={"numbering": numbering, "toc": toc})


def test_each_tool_is_a_numbered_section_under_its_chapter(tdeps):
    after = blk("free_text", title="After", text="Body after.")
    html = do_render(tdeps, chapter_layout(blk("superset_exports"), after))["html"]
    assert headings(html) == ["2.1 Alpha results", "2.2 StrongREJECT (Mijke)"]
    assert text(soup(html).find(id=f"block-{after['instance_id']}").find("h2")) == "2.3 After"
    first, second = tool_sections(html)
    assert [h.get_text(strip=True) for h in first.find_all("h4")] == ["By register", "By register", "By category"]
    assert [h.get_text(strip=True) for h in second.find_all("h4")] == ["Refusals"]
    assert "Exported results" not in text(soup(html))                     # no heading of the whole block


def test_the_tools_are_in_the_table_of_contents_under_the_chapter(tdeps):
    exports = blk("superset_exports")
    html = do_render(tdeps, chapter_layout(exports))["html"]
    nav = soup(html).find(id="toc")
    chapter_li = [li for li in nav.find_all("li") if text(li.find("a")) == "2 Tests"][0]
    assert [text(a) for a in chapter_li.find("ol").find_all("a")] == ["2.1 Alpha results",
                                                                      "2.2 StrongREJECT (Mijke)"]
    ids = [s["id"] for s in tool_sections(html)]
    assert [a["href"] for a in chapter_li.find("ol").find_all("a")] == [f"#{i}" for i in ids]
    assert ids[0] == f"block-{exports['instance_id']}" and len(set(ids)) == 2


def test_without_numbering_the_sections_are_the_tool_names(tdeps):
    html = do_render(tdeps, chapter_layout(blk("superset_exports"), numbering=False))["html"]
    assert headings(html) == ["Alpha results", "StrongREJECT (Mijke)"]


def test_a_tool_unchecked_is_left_out_and_the_numbers_close_up(tdeps):
    after = blk("free_text", title="After", text="Body after.")
    html = do_render(tdeps, chapter_layout(blk("superset_exports", dashboards=["11"]), after))["html"]
    assert headings(html) == ["2.1 StrongREJECT (Mijke)"]
    assert text(soup(html).find(id=f"block-{after['instance_id']}").find("h2")) == "2.2 After"


def test_nothing_saved_is_one_section_saying_so(deps):
    exports = blk("superset_exports")
    result = do_render(deps, snap([exports], project="C", system="C_V1", document={"numbering": True}))
    assert headings(result["html"]) == ["1 Exported results"]
    assert "Save to report" in text(tool_sections(result["html"])[0])
    assert status_of(result, exports["instance_id"])["status"] == "empty"


def test_one_status_for_the_block_whatever_its_sections(tdeps):
    exports = blk("superset_exports")
    result = do_render(tdeps, chapter_layout(exports))
    assert [s["status"] for s in result["block_statuses"] if s["instance_id"].startswith(exports["instance_id"])] \
        == ["ok"]


def commentary_of(section):
    box = section.find(class_="commentary", recursive=False)
    return text(box) if box else None


def test_each_tool_prints_its_own_commentary_after_its_plots(tdeps):
    html = do_render(tdeps, chapter_layout(blk("superset_exports", comments={"11": "Refusals held **everywhere**."})))["html"]
    first, second = tool_sections(html)
    assert commentary_of(first) is None
    box = second.find(class_="commentary", recursive=False)
    assert box.find(class_="commentary-caption").get_text() == "Commentary"
    assert "Refusals held" in box.get_text()
    assert box.find("strong").get_text() == "everywhere"                    # light formatting, as a section's commentary
    assert second.find("img").find_next(class_="commentary") is second.find(class_="commentary", recursive=False)


def test_the_tool_commentary_goes_before_when_the_section_says_so(tdeps):
    html = do_render(tdeps, chapter_layout(blk("superset_exports", comments={"10": "Bias held."},
                                              commentary_position="before")))["html"]
    first = tool_sections(html)[0]
    box = first.find(class_="commentary", recursive=False)
    assert text(box) == "Commentary Bias held."
    assert box.find_next("img") is first.find("img")
    assert first.find("h2").find_next(class_="commentary") is box


def test_an_unwritten_tool_commentary_prints_nothing(tdeps):
    html = do_render(tdeps, chapter_layout(blk("superset_exports", comments={"10": "Write this section.", "11": " "})))[
        "html"]
    assert [commentary_of(s) for s in tool_sections(html)] == [None, None]


def test_the_section_commentary_prints_before_the_first_tool(tdeps):
    exports = blk("superset_exports", commentary="About all the tools.")
    html = do_render(tdeps, chapter_layout(exports))["html"]
    first, second = tool_sections(html)
    assert html.count("About all the tools.") == 1
    lead = first.find(class_="commentary")
    assert text(lead) == "Commentary About all the tools."
    assert lead.find_next("h2") is first.find("h2")                          # before the first tool's heading
    assert commentary_of(second) is None


def test_the_tools_are_numbered_in_the_pdf_and_its_contents(tdeps):
    pages = pdf_pages(do_render(tdeps, chapter_layout(blk("superset_exports"), mode="pdf")))
    toc_page = next(i for i, p in enumerate(pages) if "Contents" in p)
    assert "2.1 Alpha results" in pages[toc_page] and "2.2 StrongREJECT (Mijke)" in pages[toc_page]
    body = " ".join(p for i, p in enumerate(pages) if i != toc_page)
    assert body.index("2.1 Alpha results") < body.index("2.2 StrongREJECT (Mijke)")


def test_the_tools_are_numbered_in_the_docx(tdeps):
    words = docx_all_text(docx_of(do_render(tdeps, chapter_layout(blk("superset_exports"), mode="docx"))))
    assert words.count("2.1 Alpha results") >= 1 and words.count("2.2 StrongREJECT (Mijke)") >= 1


def test_the_tools_offered_are_the_dashboards_with_saved_plots(tdeps):
    from report_renderer.context import context_for

    ctx = context_for(IDS["A"], IDS["A_V2"], deps=tdeps, mode="preview")
    choices = tdeps.registry.block("superset_exports")().choices(ctx, "dashboards")
    assert choices == [{"value": "10", "label": "Alpha results"}, {"value": "11", "label": "StrongREJECT (Mijke)"}]
