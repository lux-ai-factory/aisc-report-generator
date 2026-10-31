"""The Chart block: a simple chart drawn by the renderer from the version's own data.

No Superset screenshot is needed.

Datasets: coverage status counts (from the layout's coverage map), checklist mean scores, a chart a
tool renderer offers, a metric by evaluation, a metric by dimension. The chart is followed by a table
of the same numbers (also what DOCX falls back to).
"""
from __future__ import annotations

from collections.abc import Mapping

from markupsafe import Markup, escape
from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult, charts, normalise_tool_name

from ..coverage import STATUSES, coverage_for
from ..views import evaluation_names, load_answers, load_runs, metric_choices
from ._common import empty_result, finish

DATASETS = ["coverage_status", "checklist_scores", "tool_chart", "metric_by_evaluation", "metric_by_dimension"]
DATASET_LABELS = {"coverage_status": "Coverage status of the objectives",
                  "checklist_scores": "Mean score per checklist",
                  "tool_chart": "A chart of a tool",
                  "metric_by_evaluation": "A metric per evaluation",
                  "metric_by_dimension": "A metric per dimension"}
METRIC_DATASETS = ["metric_by_evaluation", "metric_by_dimension"]


def _requires(dataset, option) -> dict:
    values = dataset if isinstance(dataset, list) else [dataset]
    return {"if": {"properties": {"dataset": {"enum": values}}, "required": ["dataset"]},
            "then": {"required": [option]}}


class ChartBlock(BaseBlockRenderer):
    type_id = "chart"
    title = "Chart"
    contract_version = 1
    description = "A chart drawn in the report from this version's data."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dataset": {"enum": DATASETS, "title": "What to chart", "description": "The numbers the chart shows.",
                        "x-aisc-enum-labels": dict(DATASET_LABELS)},
            "tool_chart": {"type": "object", "required": ["tool", "chart"], "additionalProperties": False,
                           "properties": {"tool": {"type": "string", "minLength": 1},
                                          "chart": {"type": "string", "minLength": 1}},
                           "title": "Test chart", "description": "Which chart of which test.",
                           "x-aisc-reference": True, "x-aisc-show-if": {"dataset": ["tool_chart"]}},
            "metric": {"type": "object", "required": ["tool", "metric"], "additionalProperties": False,
                       "properties": {"tool": {"type": "string", "minLength": 1},
                                      "metric": {"type": "string", "minLength": 1}},
                       "title": "Metric", "description": "Which measurement to chart.",
                       "x-aisc-reference": True, "x-aisc-show-if": {"dataset": list(METRIC_DATASETS)}},
            "dimension": {"type": "string", "minLength": 1, "title": "Dimension",
                          "description": "Group the measurements by this dimension.",
                          "x-aisc-show-if": {"dataset": ["metric_by_dimension"]}, "x-aisc-prose": False},
            "runs": {"enum": ["latest", "each"], "title": "Runs", "description": "The latest run, or one chart per run.",
                     "x-aisc-enum-labels": {"latest": "Latest run", "each": "Each run"}, "x-aisc-more": True},
            "show_table": {"type": "boolean", "title": "Show the table",
                           "description": "Adds a table of the same numbers under the chart.", "x-aisc-more": True},
            "max_bars": {"type": "integer", "minimum": 3, "maximum": 40, "title": "Most bars",
                         "description": "Draws at most this many bars; the table lists all.", "x-aisc-more": True},
            "orientation": {"enum": ["auto", "vertical", "horizontal"], "title": "Orientation",
                            "description": "Direction of the bars.",
                            "x-aisc-enum-labels": {"auto": "Automatic", "vertical": "Vertical bars",
                                                   "horizontal": "Horizontal bars"},
                            "x-aisc-more": True},
        },
        "allOf": [_requires("tool_chart", "tool_chart"), _requires(METRIC_DATASETS, "metric"),
                  _requires("metric_by_dimension", "dimension")],
    }
    default_options = {"dataset": "coverage_status", "runs": "latest", "show_table": True, "max_bars": 20,
                       "orientation": "auto"}
    reads = ("platform", "engine", "controls", "control_objectives")
    choice_options = ("tool_chart", "metric", "dimension")

    # data

    def load(self, ctx, options):
        t = ctx.t
        number = ctx.system["number"]
        dataset = options["dataset"]
        if dataset == "coverage_status":
            co = ctx.data.control_objectives
            newest = co.newest_newer_assessment()
            if co.assessment() is None:
                return {"empty": t("No control objectives for version {number}.", number=number)}
            ids = co.objective_ids()
            coverage = coverage_for(ctx, ids, ctx.report.coverage_links)
            series = [{"label": t(st), "value": sum(1 for c in coverage.values() if c.status == st)}
                      for st in STATUSES]
            return {"charts": [{"title": t("Coverage status of the objectives"), "value_format": "number",
                                "axis_min": 0, "axis_max": None, "series": series}], "newest": newest}
        if dataset == "checklist_scores":
            view = load_answers(ctx)
            newest = None if view.missing_db else ctx.data.controls.newest_newer_answer(newer=ctx.data.newer)
            scored = sorted((ca for ca in view.checklists if ca.mean is not None),
                            key=lambda ca: (ca.checklist["title"] or "", ca.checklist["id"]))
            if not scored:
                return {"empty": t("No scored checklist answers for version {number}.", number=number)}
            series = [{"label": ca.checklist["title"], "value": ca.mean} for ca in scored]
            return {"charts": [{"title": t("Mean score per checklist"), "value_format": "number", "axis_min": 0,
                                "axis_max": 5, "series": series}], "newest": newest}
        newest = ctx.data.engine.newest_newer_evaluation()
        if dataset == "tool_chart":
            return {**self._tool_chart(ctx, options), "newest": newest}
        metric = options["metric"]
        key = normalise_tool_name(metric["tool"])
        names = evaluation_names(ctx)
        view = load_runs(ctx, statuses=["Done"], metrics=[metric], names=names)
        values: list[tuple[str, float]] = []
        by_group: dict[str, list[float]] = {}
        for ev in view.evaluations:
            scores = []
            for rv in ev.runs:
                if normalise_tool_name(rv.tool.get("display_name") or rv.tool.get("name") or "") != key:
                    continue
                for m in rv.run.measurements:
                    if m.get("score") is None:
                        continue
                    scores.append(float(m["score"]))
                    dims = m.get("dimensions") or {}
                    group = dims.get(options.get("dimension")) if isinstance(dims, Mapping) else None
                    by_group.setdefault(str(group) if group is not None else "unknown", []).append(float(m["score"]))
            if scores:
                k = names.get(ev.evaluation["pid"], (None,))[0]
                values.append((t("Evaluation {number}", number=k), sum(scores) / len(scores)))
        if dataset == "metric_by_evaluation":
            if not values:
                return {"empty": t("No {metric} results of {tool} for version {number}.", metric=metric["metric"],
                                   tool=metric["tool"], number=number), "newest": newest}
            series = [{"label": label, "value": v} for label, v in values]
            title = t("{tool}: {metric} per evaluation", tool=metric["tool"], metric=metric["metric"])
        else:
            if not by_group:
                return {"empty": t("No {metric} results of {tool} for version {number}.", metric=metric["metric"],
                                   tool=metric["tool"], number=number), "newest": newest}
            series = [{"label": g, "value": sum(v) / len(v)} for g, v in sorted(by_group.items())]
            title = t("{tool}: {metric} per {dimension}", tool=metric["tool"], metric=metric["metric"],
                      dimension=options["dimension"])
        # a metric can be negative (a difference, a bias score): the axis then starts below the lowest value
        return {"charts": [{"title": title, "value_format": "number", "axis_min": None, "axis_max": None,
                            "series": series}], "newest": newest}

    def _tool_chart(self, ctx, options):
        t = ctx.t
        wanted = options["tool_chart"]
        renderer = ctx.data.tools.tool_for({"display_name": wanted["tool"], "name": None, "package_name": None})
        if renderer is None or wanted["chart"] not in (getattr(renderer, "chart_ids", {}) or {}):
            return {"unavailable": True}
        names = evaluation_names(ctx)
        view = load_runs(ctx, statuses=["Done"], tools=[wanted["tool"]], names=names)
        runs = [(ev, rv) for ev in view.evaluations for rv in ev.runs]
        if options["runs"] == "latest":
            runs = runs[-1:]
        found = []
        for ev, rv in runs:
            for spec in renderer.charts(rv.run) or []:
                if spec.get("id") == wanted["chart"]:
                    spec = dict(spec)
                    if options["runs"] == "each":
                        spec["title"] = names.get(ev.evaluation["pid"], (None, spec.get("title", "")))[1]
                    found.append(spec)
        if not found:
            return {"empty": t("No {tool} results for version {number}.", tool=wanted["tool"],
                               number=ctx.system["number"])}
        return {"charts": found}

    # drawing

    def _format(self, ctx, value, value_format):
        if value is None:
            return ctx.t("n/a")
        if value_format == "percent":
            return ctx.percent(value)
        return ctx.number(f"{value:g}")

    def render(self, data, options, ctx):
        t = ctx.t
        if data.get("unavailable"):
            return BlockResult(html=f'<p class="placeholder">{escape(t("This chart is not available on this platform."))}</p>',
                               status="error", notices=[])
        if "empty" in data:
            return empty_result(data["empty"])
        notices: list[str] = []
        parts: list[Markup] = []
        max_bars = options["max_bars"]
        for spec in data["charts"]:
            series = list(spec.get("series") or [])
            drawn = series[:max_bars]
            if len(series) > max_bars:
                notices.append(t("{count} more groups are not shown.", count=len(series) - max_bars))
            if options["orientation"] == "vertical":
                kind = "bar"
            elif options["orientation"] == "horizontal":
                kind = "hbar"
            else:
                long = any(len(str(s.get("label", ""))) > 12 for s in drawn)
                kind = "hbar" if len(drawn) > 6 or long else "bar"
            draw = {"id": spec.get("id", "chart"), "title": spec.get("title", ""), "kind": kind,
                    "value_format": spec.get("value_format", "number"), "axis_min": spec.get("axis_min"),
                    "axis_max": spec.get("axis_max"), "series": drawn}
            if spec.get("note"):
                draw["note"] = spec["note"]
            try:
                svg = charts.svg(draw, ctx.chart_colours, decimal_separator=ctx.decimal_separator,
                                 percent_format=ctx.percent_format)
            except ValueError:
                return BlockResult(html=f'<div class="error-box"><p>{escape(t("This chart could not be drawn."))}</p></div>',
                                   status="error", notices=notices)
            rows = [(s.get("label", ""), self._format(ctx, s.get("value"), draw["value_format"])) for s in series]
            parts.append(Markup(self.render_package_template(
                "templates/chart.html.j2", svg=svg, kind=kind, title=draw["title"], rows=rows,
                show_table=options["show_table"], t=t)))
        return finish(Markup("").join(parts), notices, newest_newer=data.get("newest"), t=t)

    # choices

    def choices(self, ctx, option_name) -> list[dict]:
        if option_name == "metric":
            return metric_choices(ctx)
        if option_name == "dimension":
            keys: set[str] = set()
            for ev in load_runs(ctx, statuses=None).evaluations:
                for rv in ev.runs:
                    for m in rv.run.measurements:
                        if isinstance(m.get("dimensions"), Mapping):
                            keys.update(str(k) for k in m["dimensions"])
            return [{"value": k, "label": k} for k in sorted(keys)]
        if option_name == "tool_chart":
            out = []
            tools = [c["value"] for c in ctx.data.engine.tool_choices()]
            for cls in ctx.data.tools.tool_renderers():
                for tool in tools:
                    if not cls.matches({"display_name": tool}):
                        continue
                    for chart_id, label in (getattr(cls, "chart_ids", {}) or {}).items():
                        out.append({"value": {"tool": tool, "chart": chart_id}, "label": f"{tool}: {label}"})
            return out
        return []
