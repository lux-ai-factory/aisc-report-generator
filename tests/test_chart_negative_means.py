"""The Chart block with a metric that can be negative: "A metric per evaluation" and
"per dimension" set axis_min 0, so a negative mean became a bar of height 0 under its label. The axis now
starts below the lowest value for those two datasets; counts and checklist means keep 0."""
import re
from types import SimpleNamespace

import pytest

from report_renderer.blocks import chart as chart_module
from report_renderer.context import DEFAULT_CHART_COLOURS
from report_renderer.views import EvaluationView, RunsView, RunView


def _ctx():
    return SimpleNamespace(t=lambda s, **k: s.format(**k), system={"number": 2},
                           data=SimpleNamespace(engine=SimpleNamespace(newest_newer_evaluation=lambda: None)),
                           number=lambda v: v, percent=lambda v: f"{v}%", chart_colours=DEFAULT_CHART_COLOURS,
                           decimal_separator=".", percent_format="{value}%")


def _view(scores_by_eval):
    evs = []
    for pid, scores in scores_by_eval.items():
        ms = [{"score": s, "dimensions": {"group": f"g{i}"}} for i, s in enumerate(scores)]
        run = RunView(tool={"display_name": "Bias", "name": "bias"}, components=[], status="Done",
                      run=SimpleNamespace(measurements=ms), artifacts=[])
        evs.append(EvaluationView(evaluation={"pid": pid}, runs=[run], unmatched=[], unmatched_count=0))
    return RunsView(evaluations=evs, unversioned=0)


@pytest.mark.parametrize("dataset", ["metric_by_evaluation", "metric_by_dimension"])
def test_a_negative_mean_is_drawn_below_the_zero_line(monkeypatch, dataset):
    view = _view({1: [-0.4], 2: [0.2]}) if dataset == "metric_by_evaluation" else _view({1: [-0.4, 0.2]})
    monkeypatch.setattr(chart_module, "load_runs", lambda ctx, **kw: view)
    monkeypatch.setattr(chart_module, "evaluation_names", lambda ctx: {1: (1, "E1"), 2: (2, "E2")})
    block = chart_module.ChartBlock()
    options = {**block.default_options, "dataset": dataset, "metric": {"tool": "Bias", "metric": "bias"},
               "dimension": "group"}
    ctx = _ctx()
    data = block.load(ctx, options)
    assert data["charts"][0]["axis_min"] is None
    html = block.render(data, options, ctx).html
    heights = [float(h) for h in re.findall(r'<rect[^>]*\bheight="([0-9.]+)"', html)]
    widths = [float(w) for w in re.findall(r'<rect[^>]*\bwidth="([0-9.]+)"', html)]
    # every bar has a size: the negative one is no longer clipped to nothing
    assert all(v > 0 for v in heights) and all(v > 0 for v in widths)


def test_a_spec_without_axis_min_is_not_forced_to_zero():
    block = chart_module.ChartBlock()
    data = {"charts": [{"title": "t", "series": [{"label": "a", "value": -0.4}, {"label": "b", "value": 0.2}]}]}
    html = block.render(data, {**block.default_options, "orientation": "vertical"}, _ctx()).html
    heights = [float(h) for h in re.findall(r'<rect[^>]*\bheight="([0-9.]+)"', html)]
    assert heights and all(v > 0 for v in heights)
