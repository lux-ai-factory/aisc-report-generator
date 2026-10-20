"""Summary / coverage block.

Markup the tests rely on: one row per objective with `data-objective="<ID>"` holding its status
text, and one count per status with `data-coverage-count="<status>"`.
Alpha v2: objectives R1.1, R2.1, R4.1, R5.1; cl-1's v2 mean score is 2.5 (below 3).
"""
from importlib.metadata import EntryPoint

import pytest

from conftest import IDS, block, need, render, render_one, section, text

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


def test_status_per_objective(deps):
    _, s, node, _ = render_one(deps, "summary_coverage", links=LINKS)
    rows = statuses(node)
    assert sorted(rows) == ["R1.1", "R2.1", "R4.1", "R5.1"]
    assert status_word(rows["R1.1"]) == "evidence, attention"   # checklist mean 2.5 < 3
    assert status_word(rows["R2.1"]) == "no evidence"           # MLA-Reject ran on v1 only
    assert status_word(rows["R4.1"]) == "evidence"
    assert status_word(rows["R5.1"]) == "not covered"
    assert "LangBiTe" in rows["R1.1"] and "Transparency checklist" in rows["R1.1"] or "cl-1" in rows["R1.1"]


# a tool verdict of fail
def test_a_failing_verdict_is_attention(make_deps):
    build = need("report_renderer.registry", "build_registry")
    reg = build(entry_points=[EntryPoint(name="m", value="plugins_fixture.tools:FailingMysteryVerdict",
                                         group="aisc_report.tools")])
    _, _, node, _ = render_one(make_deps(registry=reg), "summary_coverage", links=LINKS)
    assert status_word(statuses(node)["R4.1"]) == "evidence, attention"


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


def test_counts_per_status(deps):
    _, _, node, _ = render_one(deps, "summary_coverage", links=LINKS)
    counts = {el["data-coverage-count"]: el.get_text(strip=True) for el in node.find_all(attrs={"data-coverage-count": True})}
    assert {k: v for k, v in counts.items()} == {"evidence": "1", "evidence, attention": "1",
                                                 "no evidence": "1", "not covered": "1"}


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
