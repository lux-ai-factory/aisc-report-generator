"""Test results: readable evaluation names, the metric filter, tool options, and the dedicated tool
renderers in place of the generic table.

Seed (seed_tools.sql), Mike v2 evaluations by created_at: 1 = StrongREJECT without scores, 2 = LangBiTe +
StrongREJECT, 3 = Promptfoo (partial), 4 = Promptfoo (all six), 5 = Failed Promptfoo (no measurements).
"""
import inspect

import pytest

from conftest import IDS, need, text, window
from v2_block_helpers import (Recorder, need_tool_package, notices_and_text, one, registry_with_tool)

pytestmark = pytest.mark.db


def headings(node):
    return [" ".join(h.get_text(" ").split()) for h in node.find_all("h3")]


# Readable names.

def test_evaluations_are_named_by_number_and_tools(deps):
    t, st, node, _ = one(deps, "test_results", statuses=["Done", "Failed"])
    assert headings(node) == ["Evaluation 1: StrongREJECT", "Evaluation 2: LangBiTe, StrongREJECT",
                              "Evaluation 3: Promptfoo", "Evaluation 4: Promptfoo", "Evaluation 5: Promptfoo"]
    assert "Evaluation f2e00000" not in t


def test_the_number_does_not_depend_on_the_filters(deps):
    _, _, node, _ = one(deps, "test_results", selection=window("2026-09-19T11:00", "2026-09-19T11:01"))
    assert headings(node) == ["Evaluation 4: Promptfoo"]
    _, _, node, _ = one(deps, "test_results", tools=["StrongREJECT"])
    # the tool list names every run of the evaluation, whatever the tools filter
    assert headings(node) == ["Evaluation 1: StrongREJECT", "Evaluation 2: LangBiTe, StrongREJECT"]


def test_more_than_three_tools_and_no_run(deps, monkeypatch):
    """Three extra fake runs on evaluation 2 and none on evaluation 3, patched into
    report_renderer.data.engine.runs(), the query the readable name is built from."""
    import report_renderer.data.engine as engine

    real = engine.runs

    def runs(project_id, system_id, *, sources, evaluation_ids, selection=None):
        rows = [r for r in real(project_id, system_id, sources=sources, evaluation_ids=evaluation_ids,
                                selection=selection)
                if r["evaluation_id"] != 73]
        if 72 in list(evaluation_ids):
            for i, name in enumerate(("Tool C", "Tool D", "Tool E")):
                rows.append({"id": 99000 + i, "pid": f"f2ea0000-0000-4000-8000-00000009900{i}",
                             "name": name.replace(" ", ""), "status": "Done", "evaluation_id": 72,
                             "display_name": name, "plugin_name": name.replace(" ", ""),
                             "package_name": "fake-" + name[-1].lower(), "version": "1"})
        return rows

    monkeypatch.setattr(engine, "runs", runs)
    _, _, node, _ = one(deps, "test_results", selection=window("2026-09-19T09:00", "2026-09-19T10:01"))
    assert headings(node) == ["Evaluation 2: LangBiTe, StrongREJECT, Tool C, +2 more", "Evaluation 3"]


# Meta line.

def test_meta_line_with_time_and_reference(deps):
    t, *_ = one(deps, "test_results", selection=window("2026-09-19T09:00", "2026-09-19T09:01"))
    assert "Status: Done | Date: 2026-09-19 09:00 UTC | Reference: f2e00000" in t


# Evaluation choices.

# ToolRun and measurements.

def test_measurements_carry_description_and_error(sources):
    measurements = need("report_renderer.data.engine", "measurements")
    rows = measurements(IDS["M"], IDS["M_V2"], sources=sources, observation_ids=[7101])
    assert rows, "the seed has four measurements on observation 7101"
    missing = {"description", "error"} - set(rows[0])
    assert not missing, f"missing feature: measurements() does not return {sorted(missing)}"
    assert {r["description"] for r in rows} >= {"No score produced", "Not measured"}


def test_tool_run_has_name_number_and_measurement_descriptions(make_deps):
    Recorder.seen = []
    deps = make_deps(registry=registry_with_tool(Recorder))
    one(deps, "test_results")
    assert len(Recorder.seen) == 2, "two Done StrongREJECT runs in Mike v2"
    by_number = {s["run"].evaluation.get("number"): s["run"] for s in Recorder.seen}
    assert set(by_number) == {1, 2}, "missing feature: ToolRun.evaluation['number']"
    assert by_number[2].evaluation.get("name") == "Evaluation 2: LangBiTe, StrongREJECT"
    first = by_number[1].measurements[0]
    assert "description" in first and "error" in first, "missing feature: measurement description and error"
    assert first["description"] == "No score produced"


# Metric filter.

def test_only_selected_metrics_reach_the_tool_renderer(make_deps):
    Recorder.seen = []
    deps = make_deps(registry=registry_with_tool(Recorder))
    one(deps, "test_results", metrics=[{"tool": "StrongREJECT", "metric": "Jailbreak Resistance"}])
    assert Recorder.seen
    for s in Recorder.seen:
        assert [m["name"] for m in s["run"].measurements] == ["Jailbreak Resistance"]


def test_only_selected_metrics_in_the_generic_table(make_deps):
    deps = make_deps(registry=need("report_renderer.registry", "build_registry")(entry_points=[]))
    t, *_ = one(deps, "test_results", metrics=[{"tool": "Promptfoo", "metric": "n_tests"}])
    assert "n_tests" in t and "mean_latency_ms" not in t and "Jailbreak Resistance" not in t


def test_a_run_left_without_metrics_is_still_listed(make_deps):
    deps = make_deps(registry=need("report_renderer.registry", "build_registry")(entry_points=[]))
    t, _, node, _ = one(deps, "test_results", metrics=[{"tool": "Promptfoo", "metric": "n_tests"}])
    runs = node.find_all("div", class_="run")
    lb = [r for r in runs if "LangBiTe" in text(r)]
    assert lb, "the LangBiTe run is still listed"
    assert "No selected metrics in this run." in text(lb[0])
    assert "Overall Pass Rate" not in t


def test_metric_choices(deps):
    ctx = need("report_renderer.context", "context_for")(IDS["M"], IDS["M_V2"], deps=deps, mode="preview")
    choices = deps.registry.block("test_results")().choices(ctx, "metrics")
    assert choices, "missing feature: choices for test_results.metrics"
    values = [(c["value"]["tool"], c["value"]["metric"]) for c in choices]
    assert len(values) == 21 and len(set(values)) == 21
    assert ("Promptfoo", "pass_rate") in values and ("LangBiTe", "Overall Pass Rate") in values
    assert values == sorted(values, key=lambda v: (v[0], v[1])) or \
        values == sorted(values, key=lambda v: (v[0].casefold(), v[1].casefold()))
    assert all(c["label"] == f"{c['value']['tool']}: {c['value']['metric']}" for c in choices)


def test_metrics_default_all_is_today(deps):
    t_all, *_ = one(deps, "test_results", metrics="all")
    t_def, *_ = one(deps, "test_results")
    assert t_all == t_def


# Tool options.

def test_tool_options_defaults(make_deps):
    Recorder.seen = []
    deps = make_deps(registry=registry_with_tool(Recorder))
    one(deps, "test_results")
    assert Recorder.seen[0]["tool_options"] == {"show_charts": True, "detail": "full"}, \
        "missing feature: ctx.tool_options from the test_results options"


def test_tool_options_from_the_block(make_deps):
    Recorder.seen = []
    deps = make_deps(registry=registry_with_tool(Recorder))
    one(deps, "test_results", show_charts=False, detail="summary")
    assert Recorder.seen and Recorder.seen[0]["tool_options"] == {"show_charts": False, "detail": "summary"}


# Artifacts: names and sizes only.

def test_artifact_contents_never_reach_the_report(deps):
    t, _, _, result = one(deps, "test_results", show_artifacts=True)
    assert "strongreject_per_prompt.csv" in t and "promptfoo_results.json" in t
    assert "HARMFULPROMPTCONTENT" not in result["html"]


def test_the_artifact_query_selects_name_and_size_only():
    """The only artifact query selects no content column."""
    from report_renderer.data import engine

    src = inspect.getsource(engine)
    assert "engine.aisc_backend_artifact" in src
    for chunk in src.split("def ")[1:]:
        if "engine.aisc_backend_artifact" in chunk:
            assert "a.data" not in chunk and "storage_container" not in chunk, chunk[:200]


# Example Assistant's tools have dedicated renderers.

def test_the_example_assistant_tools_have_dedicated_renderers(deps):
    for module, cls in (("aisc_report_plugin_langbite", "LANGBITEToolRenderer"),
                        ("aisc_report_plugin_strongreject", "STRONGREJECTToolRenderer"),
                        ("aisc_report_plugin_promptfoo", "PROMPTFOOToolRenderer")):
        need_tool_package(module, cls)
    t, st, *_ = one(deps, "test_results")
    joined = notices_and_text(t, st)
    for tool in ("LangBiTe", "StrongREJECT", "Promptfoo"):
        assert f"No dedicated renderer for {tool}" not in joined
