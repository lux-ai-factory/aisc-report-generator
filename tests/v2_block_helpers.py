"""Helpers of the block tests. Test infrastructure only.

Markup contracts these tests rely on:
- key_figures: one tile per figure carrying `data-figure="<figure id>"` (version, risks, objectives,
  coverage, tests, checklists); tool headline tiles carry `data-figure="tool"`.
- chart: every drawn chart sits in `<figure class="chart" data-kind="bar|hbar">` holding the SVG.
- changes_since: one element per part carrying `data-changes="card|objectives|tests|controls"`.
"""
from __future__ import annotations

import pytest
from aisc_report_plugin_interface import BaseToolRenderer

from conftest import IDS, block, need, render, section, status_of, text

NEW_BLOCKS = ("chart", "key_figures", "changes_since")

#: the coverage map the tests use on Mike v2, in the shape of a snapshot's coverage_links
MIKE_MAP = [
    {"objective_id": "R1.1", "tests": ["LangBiTe"], "checklists": ["cl-m1"]},
    {"objective_id": "R2.1", "tests": ["Promptfoo"], "checklists": []},
    {"objective_id": "R4.1", "tests": ["MLA-Reject"], "checklists": []},
]
#: Mike v2 with MIKE_MAP: R1.1 evidence (cl-m1 mean 4.5), R2.1 evidence, R4.1 no evidence, R5.1 not covered
MIKE_V2_STATUSES = {"R1.1": "evidence", "R2.1": "evidence", "R4.1": "no evidence", "R5.1": "not covered"}
REQUIREMENT_GROUPS = ["R1 Human Agency and Oversight", "R2 Data Governance", "R3 Record Keeping", "R4 Accuracy",
                      "R5 Transparency"]


def block_class(deps, type_id):
    """A built-in block type of the renderer, or a FAILED test naming the missing one."""
    cls = deps.registry.block(type_id)
    if cls is None:
        pytest.fail(f"missing feature: built-in block type {type_id}", pytrace=False)
    return cls


def assert_option(deps, type_id, name):
    cls = block_class(deps, type_id)
    props = cls.full_options_schema().get("properties", {})
    if name not in props:
        pytest.fail(f"missing feature: option {name} of block {type_id}", pytrace=False)
    return props[name]


def v2_snapshot(blocks, *, project="M", system="M_V2", coverage_links=None, mode="preview", **extra):
    from conftest import snapshot

    s = snapshot(blocks, project=project, system=system, mode=mode)
    if coverage_links is not None:
        s["coverage_links"] = coverage_links
    s.update(extra)
    return s


def render_snapshot(deps, snap):
    return need("report_renderer.document", "render")(snap, deps)


def one(deps, block_type, *, project="M", system="M_V2", coverage_links=None, allow_error=False, selection=None,
        **options):
    """Render a layout of one block; returns (text, status, node, result). An `error` status caused by
    options the block does not accept or by a missing block type FAILS as a missing feature.
    `selection` is the report's data selection (conftest.window)."""
    b = block(block_type, **options)
    extra = {"snapshot_version": 3, "selection": selection} if selection is not None else {}
    result = render_snapshot(deps, v2_snapshot([b], project=project, system=system, coverage_links=coverage_links,
                                               **extra))
    st = status_of(result, b["instance_id"])
    node = section(result["html"], b["instance_id"])
    if st["status"] == "error" and not allow_error:
        joined = " ".join(st["notices"])
        if "Unknown block type" in joined or "Invalid options" in joined:
            pytest.fail(f"missing feature: block {block_type} with options {sorted(options)}: {joined}",
                        pytrace=False)
    return text(node), st, node, result


def notices_and_text(t, st) -> str:
    return t + " " + " ".join(st["notices"])


def objectives_shown(node) -> list[str]:
    return sorted(el["data-objective"] for el in node.find_all(attrs={"data-objective": True}))


def risks_shown(node) -> list[str]:
    return [el["data-risk"] for el in node.find_all(attrs={"data-risk": True})]


def figure(node, fid):
    el = node.find(attrs={"data-figure": fid})
    assert el is not None, f"no tile data-figure={fid!r} in the key figures (markup contract of the v2 tests)"
    return text(el)


def changes_part(node, part):
    el = node.find(attrs={"data-changes": part})
    assert el is not None, f"no element data-changes={part!r} in changes_since (markup contract of the v2 tests)"
    return text(el)


def charts(node):
    return node.find_all("figure", class_="chart")


def table_rows(node) -> list[list[str]]:
    rows = []
    for tr in node.find_all("tr"):
        cells = [" ".join(c.get_text(" ").split()) for c in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    return rows


def registry_with_tool(tool_cls):
    """Built-ins only (no installed tool packages), plus one test tool renderer."""
    reg = need("report_renderer.registry", "build_registry")(entry_points=[])
    reg.register_tool(tool_cls, "tests.v2_block_helpers")
    return reg


class Recorder(BaseToolRenderer):
    """A StrongREJECT tool renderer that records what it is given (runs and ctx.tool_options)."""

    tool_names = ("StrongREJECT",)
    seen: list = []

    def render(self, run, ctx):
        Recorder.seen.append({"run": run, "tool_options": getattr(ctx, "tool_options", None)})
        return "<p>RECORDER-OUTPUT</p>"


def need_tool_package(module, cls):
    """The dedicated tool renderer package. These are optional packages, not dependencies of the
    renderer: a test of one is skipped when it is not installed (see test_standalone_packaging.py)."""
    pytest.importorskip(module, reason=f"optional tool renderer {module} is not installed")
    return need(module, cls)


__all__ = ["IDS", "block", "render"]
