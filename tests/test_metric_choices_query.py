"""The metric choices (the Test results and Chart blocks' `metrics` option) come from one query that
returns the distinct (tool, metric) pairs, not from loading every measurement of the project.

The output must stay what it was: `old_metric_choices` below is the earlier implementation, kept here as
the reference, and both are compared on every project and version of the report bed. The seed holds
the cases the naming hangs on: a run matched to its observations by the "{package}::{plugin} (v{version})"
tag, an observation no run claims (left out), a run with no plugin configuration (named by the run, and
given every observation of its evaluation because it is the evaluation's only run), unversioned
evaluations, and projects with no evaluation at all."""
import dataclasses

import pytest

from conftest import IDS, need

pytestmark = pytest.mark.db

VERSIONS = [("A", "A_V1"), ("A", "A_V2"), ("A", "A_V3"), ("B", "B_V1"), ("C", "C_V1"), ("E", "E_V1"),
            ("E", "E_V2"), ("M", "M_V1"), ("M", "M_V2"), ("D", "D_V1")]


def _ctx(deps, project, system):
    return need("report_renderer.context", "context_for")(IDS[project], IDS[system], deps=deps, mode="preview")


def old_metric_choices(ctx) -> list[dict]:
    """The earlier implementation: every run and measurement of the project, loaded in full."""
    from report_renderer.selection import Selection
    from report_renderer.views import load_runs

    pairs: set[tuple[str, str]] = set()
    every = dataclasses.replace(ctx, report=dataclasses.replace(ctx.report, selection=Selection(other_versions=True)))
    for ev in load_runs(every, statuses=None).evaluations:
        for rv in ev.runs:
            tool = rv.tool.get("display_name") or rv.tool.get("name") or ""
            for m in rv.run.measurements:
                metric = m.get("metric") or m.get("name")
                if tool and metric:
                    pairs.add((tool, metric))
    ordered = sorted(pairs, key=lambda p: (p[0].casefold(), p[1].casefold(), p[0], p[1]))
    return [{"value": {"tool": tool, "metric": metric}, "label": f"{tool}: {metric}"} for tool, metric in ordered]


@pytest.mark.parametrize("project,system", VERSIONS)
def test_the_query_gives_the_same_choices_as_loading_every_measurement(deps, project, system):
    from report_renderer.views import metric_choices

    ctx = _ctx(deps, project, system)
    assert metric_choices(ctx) == old_metric_choices(ctx)


def test_the_fixture_exercises_the_naming_cases(deps):
    """Guards the comparison above: the seed still holds a run named by its plugin's display name, a run
    with no configuration named by the run itself, and an observation no run claims."""
    from report_renderer.views import metric_choices

    choices = {(c["value"]["tool"], c["value"]["metric"]) for c in metric_choices(_ctx(deps, "A", "A_V2"))}
    tools = {t for t, _ in choices}
    assert "LangBiTe" in tools and "MLA-Reject" in tools
    assert "LangBiTeEvaluationPlugin" in tools          # run 231 has no plugin configuration


def test_the_choices_never_load_the_measurements_one_by_one(deps, monkeypatch):
    import report_renderer.data.engine as engine
    from report_renderer.views import metric_choices

    def refuse(*a, **k):
        raise AssertionError("metric choices loaded every measurement")

    monkeypatch.setattr(engine, "measurements", refuse)
    monkeypatch.setattr(engine, "observations", refuse)
    ctx = _ctx(deps, "M", "M_V2")
    assert len(metric_choices(ctx)) == 21
