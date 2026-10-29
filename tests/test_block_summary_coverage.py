"""Summary / coverage block.

Markup the tests rely on: one row per objective with `data-objective="<ID>"`: its id, its label, its
description, its linked tests and checklists (by their labels) and its coverage for the pinned version
(`data-coverage="<status>"` on the coverage cell).
Alpha v2: objectives R1.1, R2.1, R4.1, R5.1; cl-1's v2 mean score is 2.5 (below 3).
"""
from importlib.metadata import EntryPoint

import pytest

from conftest import IDS, block, need, render, render_one, section, text
from v2_block_helpers import render_snapshot, v2_snapshot

pytestmark = pytest.mark.db

LINKS = [
    {"objective_id": "R1.1", "tests": ["LangBiTe"], "checklists": ["cl-1"]},
    {"objective_id": "R2.1", "tests": ["MLA-Reject"], "checklists": []},
    {"objective_id": "R4.1", "tests": ["Mystery Tool"], "checklists": []},
]


def statuses(node):
    return {el["data-objective"]: text(el) for el in node.find_all(attrs={"data-objective": True})}


def status_word(row_text):
    for st in ("evidence, attention", "not covered", "no evidence", "evidence"):
        if st in row_text:
            return st
    return None


def rows_of(node):
    return {tr["data-objective"]: [td.get_text(strip=True) for td in tr.find_all("td")]
            for tr in node.find_all("tr", attrs={"data-objective": True})}


def test_one_row_per_objective_with_label_description_links_and_coverage(deps):
    _, s, node, _ = render_one(deps, "summary_coverage", links=LINKS)
    headers = [th.get_text(strip=True) for th in node.find("table").find_all("th")]
    assert headers == ["Objective", "Label", "Description", "Tests", "Checklists", "Coverage"]
    rows = rows_of(node)
    assert sorted(rows) == ["R1.1", "R2.1", "R4.1", "R5.1"]
    assert all(len(cells) == 6 and cells[0] == oid for oid, cells in rows.items())
    assert all(cells[2] for cells in rows.values()), "an objective without its description"
    assert rows["R1.1"][3:] == ["LangBiTe", "Transparency checklist", "evidence, attention"]  # cl-1 mean 2.5 < 3
    assert rows["R2.1"][3:] == ["MLA-Reject", "", "no evidence"]     # MLA-Reject ran on v1 only
    assert rows["R4.1"][3:] == ["Mystery Tool", "", "evidence"]
    assert rows["R5.1"][3:] == ["", "", "not covered"]


def test_the_coverage_cell_names_its_status(deps):
    _, _, node, _ = render_one(deps, "summary_coverage", links=LINKS)
    cells = {el.find_parent("tr")["data-objective"]: el["data-coverage"]
             for el in node.find_all(attrs={"data-coverage": True})}
    assert cells == {"R1.1": "evidence, attention", "R2.1": "no evidence", "R4.1": "evidence",
                     "R5.1": "not covered"}


def test_a_test_linked_by_its_package_shows_its_label(deps):
    """The Evidence map names a test by its plugin's package: the table shows the plugin's label."""
    links = [{"objective_id": "R4.1", "tests": ["aisc-plugin-mystery"], "checklists": []}]
    _, _, node, _ = render_one(deps, "summary_coverage", links=links)
    assert rows_of(node)["R4.1"][3:] == ["Mystery Tool", "", "evidence"]


def test_a_test_no_plugin_knows_shows_its_name(deps):
    links = [{"objective_id": "R4.1", "tests": ["aisc-plugin-gone"], "checklists": []}]
    _, _, node, _ = render_one(deps, "summary_coverage", links=links)
    assert rows_of(node)["R4.1"][3:] == ["aisc-plugin-gone", "", "no evidence"]


# a tool verdict of fail
def test_a_failing_verdict_is_attention(make_deps):
    build = need("report_renderer.registry", "build_registry")
    reg = build(entry_points=[EntryPoint(name="m", value="plugins_fixture.tools:FailingMysteryVerdict",
                                         group="aisc_report.tools")])
    _, _, node, _ = render_one(make_deps(registry=reg), "summary_coverage", links=LINKS)
    assert rows_of(node)["R4.1"][5] == "evidence, attention"


def test_the_snapshot_map_is_shown_when_the_block_has_no_links(deps):
    b = block("summary_coverage")
    result = render_snapshot(deps, v2_snapshot([b], project="A", system="A_V2", coverage_links=LINKS))
    node = section(result["html"], b["instance_id"])
    assert rows_of(node)["R1.1"][3:] == ["LangBiTe", "Transparency checklist", "evidence, attention"]


# computed from the data, not from the other blocks of the layout
def test_works_without_the_other_blocks(deps):
    only = block("summary_coverage", links=LINKS)
    with_others = [block("test_results", tools=["LangBiTe"]), block("summary_coverage", links=LINKS)]
    a = statuses(section(render(deps, [only])["html"], only["instance_id"]))
    b = statuses(section(render(deps, with_others)["html"], with_others[1]["instance_id"]))
    assert a == b


def test_uncovered_only(deps):
    _, _, node, _ = render_one(deps, "summary_coverage", links=LINKS, show_uncovered_only=True)
    assert sorted(statuses(node)) == ["R2.1", "R5.1"]


def test_empty_without_an_assessment(deps):
    _, s, *_ = render_one(deps, "summary_coverage", project="C", system="C_V1")
    assert s["status"] == "empty"


# the choices the composer offers
def test_choices_for_links(deps):
    ctx = need("report_renderer.context", "context_for")(IDS["A"], IDS["A_V2"], deps=deps, mode="preview")
    cls = deps.registry.block("summary_coverage")
    objectives = {c["value"] for c in cls().choices(ctx, "links.objective_id")}
    tools = {c["value"] for c in cls().choices(ctx, "links.tests")}
    checklists = {c["value"] for c in cls().choices(ctx, "links.checklists")}
    assert objectives == {"R1.1", "R2.1", "R4.1", "R5.1"}
    assert {"LangBiTe", "Mystery Tool"} <= tools
    assert "cl-1" in checklists and "cl-b" not in checklists

