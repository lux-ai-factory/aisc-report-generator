"""Test results block and tool renderers. Database tests on the bed.

Alpha v2 has two Done evaluations (on the 9th of September without plugin config, on the 10th with
LangBiTe and Mystery Tool) and one Failed (on the 11th); v1, v3, unversioned and Beta evaluations carry markers.
"""
import re
from importlib.metadata import EntryPoint

import pytest

from conftest import IDS, assert_no_foreign_data, need, render_one, text, window

pytestmark = pytest.mark.db


def test_evaluations_of_the_version_by_date(deps):
    t, s, _, result = render_one(deps, "test_results")
    assert t.index("2026-09-09") < t.index("2026-09-10")
    assert "2026-09-11" not in t        # Failed: not in the default statuses
    assert_no_foreign_data(result["html"])


def test_statuses_option(deps):
    t, *_ = render_one(deps, "test_results", statuses=["Done", "Failed"])
    assert "2026-09-11" in t and "Failed" in t


def test_each_plugin_run_with_tool_components_and_status(deps):
    t, *_ = render_one(deps, "test_results", selection=window("2026-09-10T09:00", "2026-09-10T09:01"))
    assert "a2e00000" in t                      # short pid
    assert "LangBiTe" in t and "Mystery Tool" in t   # display_name
    assert "Scoring model endpoint" in t and "Holdout prompts" in t   # every input
    assert "Done" in t


def test_an_unknown_tool_gets_the_generic_table(deps):
    t, s, *_ = render_one(deps, "test_results", selection=window("2026-09-10T09:00", "2026-09-10T09:01"))
    assert "No dedicated renderer for Mystery Tool; showing raw measurements." in t + " ".join(s["notices"])
    assert "mystery_metric" in t and "pt" in t
    assert "Evaluation 2: LangBiTe, Mystery Tool" in t     # A v2: 23 (09-09), 21 (09-10), 22 (09-11)


def test_the_generic_table_stops_at_500(deps):
    _, _, node, _ = render_one(deps, "test_results", selection=window("2026-09-10T09:00", "2026-09-10T09:01"))
    assert "and 5 more" in text(node)
    cells = [td for td in node.find_all("td") if td.get_text(strip=True) == "mystery_metric"]
    assert len(cells) == 500


def test_observations_tied_to_their_run_and_the_rest_counted(deps):
    t, s, *_ = render_one(deps, "test_results", selection=window("2026-09-10T09:00", "2026-09-10T09:01"))
    assert "0.125" in t                                # LangBiTe's own observation
    assert "1 observation could not be tied to a tool." in t + " ".join(s["notices"])


def test_a_single_run_without_config_takes_every_observation(deps):
    t, *_ = render_one(deps, "test_results", selection=window("2026-09-09T09:00", "2026-09-09T09:01"))
    assert "0.5" in t


# options
def test_evaluations_and_tools_filters(deps):
    t, *_ = render_one(deps, "test_results", selection=window("2026-09-10T09:00", "2026-09-10T09:01"))
    assert "2026-09-09" not in t
    t, _, node, _ = render_one(deps, "test_results", tools=["LangBiTe"])
    # the evaluation's readable name lists all its tools whatever the filter,
    # so the filter is checked on the runs shown (one <h4> per run)
    runs = [" ".join(h.get_text(" ").split()) for h in node.find_all("h4")]
    assert "Mystery Tool" not in runs and "LangBiTe" in runs


def test_measurements_can_be_hidden(deps):
    t, *_ = render_one(deps, "test_results", show_measurements=False)
    assert "mystery_metric" not in t


def test_evaluations_without_a_version_are_counted_not_shown(deps):
    t, s, _, result = render_one(deps, "test_results")
    assert "2 evaluations are not tied to a version and are not shown." in s["notices"]
    assert "NULLMARK" not in result["html"]


def test_artifacts_by_name_and_size_never_content(deps):
    t, *_ = render_one(deps, "test_results", show_artifacts=True)
    assert "langbite-report.csv" in t and ("2048" in t or "2.0 KB" in t or "2 KB" in t)
    assert "ARTIFACTCONTENT" not in t
    t, *_ = render_one(deps, "test_results")
    assert "langbite-report.csv" not in t


def test_no_results_for_the_version(deps):
    t, s, *_ = render_one(deps, "test_results", project="C", system="C_V1")
    assert s["status"] == "empty" and "No test results for version 1." in t


def test_newer_results(deps):
    _, s, *_ = render_one(deps, "test_results")
    assert s["status"] == "stale" and "Newer results exist for version 3." in s["notices"]
    _, s, *_ = render_one(deps, "test_results", system="A_V3")
    assert s["status"] == "ok"


# the installed MLA-Reject tool renderer is used for its runs
def test_the_mla_reject_section_comes_from_its_tool_renderer(deps):
    pytest.importorskip("aisc_report_plugin_mlareject", reason="optional tool renderer, not installed")
    t, *_ = render_one(deps, "test_results", system="A_V1")
    assert "Mean score" in t and "2.500" in t      # (4.0 + 1.0 + 2.5) / 3
    assert "No dedicated renderer for MLA-Reject" not in t


def _registry(entry_points=()):
    build = need("report_renderer.registry", "build_registry")
    return build(entry_points=list(entry_points))


def _tool_ep(value, name):
    return EntryPoint(name=name, value=value, group="aisc_report.tools")


def test_a_dedicated_renderer_replaces_the_generic_table(make_deps):
    deps = make_deps(registry=_registry([_tool_ep("plugins_fixture.tools:LangBiTeTool", "lb")]))
    t, *_ = render_one(deps, "test_results", selection=window("2026-09-10T09:00", "2026-09-10T09:01"))
    assert "LANGBITE-TOOL-OUTPUT" in t
    assert "No dedicated renderer for LangBiTe" not in t


def test_a_failing_tool_renderer_falls_back_to_the_generic_table(make_deps):
    deps = make_deps(registry=_registry([_tool_ep("plugins_fixture.tools:BrokenLangBiTeTool", "lb")]))
    t, s, _, result = render_one(deps, "test_results", selection=window("2026-09-10T09:00", "2026-09-10T09:01"))
    notices = t + " ".join(s["notices"])
    assert re.search(r"The LangBiTe renderer failed \(ref [0-9a-f]{8}\)\.", notices)
    assert "bias_rate" in t and "0.125" in t          # the generic table instead
    assert "mystery_metric" in t                       # other tools unaffected
    assert "LANGBITE-RENDERER-BOOM" not in result["html"]
    assert s["status"] != "error"


# the choices offered for this block
def test_choices_are_of_the_project_and_version(deps, sources):
    reg = deps.registry
    Ctx = need("report_renderer.context", "context_for")
    ctx = Ctx(IDS["A"], IDS["A_V2"], deps=deps, mode="preview")
    tools = {c["value"] for c in reg.block("test_results")().choices(ctx, "tools")}
    assert {"LangBiTe", "Mystery Tool", "MLA-Reject"} <= tools     # every version's tools
