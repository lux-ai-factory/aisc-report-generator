"""Summary / coverage block.

Markup the tests rely on: one row per objective with `data-objective="<ID>"`: its id, its label and its
description. Tests and checklists are not yet linked to objectives in practice, so the table shows no
tests, checklists, status or counts; the coverage links still decide which objectives "only objectives without
evidence" keeps.
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


def test_one_row_per_objective_with_its_label_and_description(deps):
    _, s, node, _ = render_one(deps, "summary_coverage", links=LINKS)
    headers = [th.get_text(strip=True) for th in node.find("table").find_all("th")]
    assert headers == ["Objective", "Label", "Description"]
    rows = {tr["data-objective"]: [td.get_text(strip=True) for td in tr.find_all("td")]
            for tr in node.find_all("tr", attrs={"data-objective": True})}
    assert sorted(rows) == ["R1.1", "R2.1", "R4.1", "R5.1"]
    assert all(len(cells) == 3 and cells[0] == oid for oid, cells in rows.items())
    assert all(cells[2] for cells in rows.values()), "an objective without its description"


def test_no_tests_checklists_status_or_counts_are_shown(deps):
    t, _, node, _ = render_one(deps, "summary_coverage", links=LINKS)
    assert node.find(attrs={"data-coverage-count": True}) is None
    for shown_before in ("LangBiTe", "MLA-Reject", "not covered", "no evidence"):
        assert shown_before not in t


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
