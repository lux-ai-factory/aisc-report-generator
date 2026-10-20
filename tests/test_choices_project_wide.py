"""Tool and metric names are the project's, not one version's: a layout that names a tool is valid for
every version of the project, so the choices a reference is checked against come from every run of
the project."""
import pytest

from conftest import IDS, need

pytestmark = pytest.mark.db


def _ctx(deps, system):
    return need("report_renderer.context", "context_for")(IDS["A"], IDS[system], deps=deps, mode="preview")


def test_tool_choices_include_the_tools_of_other_versions(deps):
    tools = {c["value"] for c in deps.registry.block("test_results")().choices(_ctx(deps, "A_V2"), "tools")}
    assert "MLA-Reject" in tools and "LangBiTe" in tools        # MLA-Reject ran only against version 1


def test_metric_choices_include_the_metrics_of_other_versions(deps):
    labels = {c["label"] for c in deps.registry.block("test_results")().choices(_ctx(deps, "A_V2"), "metrics")}
    assert any(label.startswith("MLA-Reject:") for label in labels), labels


def test_another_projects_tools_never_appear(deps):
    beta = need("report_renderer.context", "context_for")(IDS["B"], IDS["B_V1"], deps=deps, mode="preview")
    tools = {c["value"] for c in deps.registry.block("test_results")().choices(beta, "tools")}
    assert "Mystery Tool" not in tools and "MLA-Reject" not in tools


def test_coverage_counts_only_the_pinned_versions_runs_even_with_other_versions_on(deps):
    """Coverage loaded the runs of the report's selection, so with other versions on, a run against
    another version counted as evidence for the pinned one. MLA-Reject ran only
    against version 1: for a version-2 report it is no evidence, whatever the selection shows."""
    from report_renderer.coverage import coverage_for
    from report_renderer.selection import from_snapshot

    context_for = need("report_renderer.context", "context_for")
    report = {"selection": from_snapshot({"other_versions": True})}
    ctx = context_for(IDS["A"], IDS["A_V2"], deps=deps, mode="preview", report=report)
    links = [{"objective_id": "O1", "tests": ["MLA-Reject"], "checklists": []}]
    assert coverage_for(ctx, ["O1"], links)["O1"].status == "no evidence"
    ctx_v1 = context_for(IDS["A"], IDS["A_V1"], deps=deps, mode="preview", report=report)
    assert coverage_for(ctx_v1, ["O1"], links)["O1"].status.startswith("evidence")
