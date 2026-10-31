"""The charts a plugin declares, drawn in Test results.

A plugin declares its charts in its contract (aisc-plugin-interface: get_metric_visualizations), the same
charts the results dashboard opens a plugin's tile with. The snapshot carries them per plugin configuration
(`declared_charts`, gathered by the composer through the platform), so the report draws what the plugin
says about its own results, with no report code per tool. For now only the tools in TOOLS (LangBiTe and
Data Drift) are drawn this way; the declared charts of any other plugin are left out.

What is drawn, from the run's measures of the chart's metrics (and its filter_dimensions):
- a table chart: a row per group of group_by_dimensions, a column per metric with the mean score; a metric
  column with the same value on every row says nothing and is left out (LangBiTe's Failed cases are each
  scored 1);
- any other chart: bars, one per group (or per metric, or per metric_label_dimension value), the mean
  score; a line chart keeps its groups in order, as bars.
Radar, scatter, KDE and CSV charts have no report form and are left out, as is a chart with no measures.
"""
from __future__ import annotations

from collections.abc import Mapping

from markupsafe import Markup, escape
from aisc_report_plugin_interface.charts import MAX_ITEMS, svg
from aisc_report_plugin_interface.tools import normalise_tool_name

from .context import DEFAULT_CHART_COLOURS

#: the tools whose declared charts the report draws, for now (normalised names)
TOOLS = frozenset(normalise_tool_name(n) for n in ("LangBiTe", "Data Drift"))
#: charts with no report form
SKIPPED = frozenset({"radar", "scatter", "kde", "csv"})
MAX_ROWS = 500


def uses_declared(tool: Mapping) -> bool:
    names = (tool.get("display_name"), tool.get("name"))
    return any(n and normalise_tool_name(n) in TOOLS for n in names)


def charts_for(report, run) -> list:
    """The charts the snapshot carries for this run's plugin configuration."""
    declared = getattr(report, "declared_charts", None) or {}
    config = (run.evaluation_plugin or {}).get("plugin_config_id")
    return list(declared.get(str(config), ())) if config is not None else []


def _dims(m) -> Mapping:
    d = m.get("dimensions")
    return d if isinstance(d, Mapping) else {}


def _score(m):
    s = m.get("score")
    return float(s) if isinstance(s, (int, float)) and not isinstance(s, bool) else None


def _measures(chart, measurements) -> list:
    metrics = set(chart.get("metrics") or ())
    wanted = chart.get("filter_dimensions") or {}
    out = []
    for m in measurements:
        if (m.get("metric") or m.get("name")) not in metrics and m.get("name") not in metrics:
            continue
        dims = _dims(m)
        if any(dims.get(k) not in values for k, values in wanted.items()):
            continue
        out.append(m)
    return out


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _number(value) -> str:
    return "" if value is None else f"{value:.4g}"


def _percent(chart) -> bool:
    """The chart's scores are ratios from 0 to 1, shown as percent (the plugin's value_format)."""
    return chart.get("value_format") == "percent"


def _as_percent(value, ctx) -> str:
    if value is None:
        return ""
    digits = f"{value * 100:.1f}".rstrip("0").rstrip(".")
    return (getattr(ctx, "percent_format", "{value}%") or "{value}%").replace(
        "{value}", digits.replace(".", getattr(ctx, "decimal_separator", ".") or "."))


def _groups(chart, ms) -> dict:
    """{group key (tuple of texts): {metric: [scores]}}, in first-seen order."""
    by = list(chart.get("group_by_dimensions") or ())
    label_dim = chart.get("metric_label_dimension")
    groups: dict = {}
    for m in ms:
        dims = _dims(m)
        metric = m.get("metric") or m.get("name")
        if by:
            key = tuple(str(dims.get(k, "")) for k in by)
        elif label_dim:
            key = (str(dims.get(label_dim, metric)),)
        else:
            key = (str(metric),)
        groups.setdefault(key, {}).setdefault(metric, []).append(_score(m))
    return groups


def _table(chart, ms, ctx) -> Markup:
    by = list(chart.get("group_by_dimensions") or ())
    metrics = [x for x in chart.get("metrics") or () if any((m.get("metric") or m.get("name")) == x for m in ms)]
    groups = _groups(chart, ms)
    rows = sorted(groups.items(), key=lambda kv: kv[0])[:MAX_ROWS]
    means = {metric: [_mean(cols.get(metric, [])) for _, cols in rows] for metric in metrics}
    # a metric that is 1 on every row only marks that the row is a listed case (LangBiTe's Failed cases):
    # it says nothing, so it is left out; any other score is shown, even on one row or when all are equal
    shown = [x for x in metrics if not (by and all(v == 1 for v in means[x]))]
    shown_as = (lambda v: _as_percent(v, ctx)) if _percent(chart) else _number
    head = "".join(f"<th>{escape(h)}</th>" for h in by + shown)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(k)}</td>" for k in key)
        + "".join(f"<td>{escape(shown_as(means[x][i]))}</td>" for x in shown) + "</tr>"
        for i, (key, _) in enumerate(rows))
    return Markup(f'<table class="declared-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>')


def _bars(chart, ms, ctx) -> Markup | None:
    groups = _groups(chart, ms)
    several = len(chart.get("metrics") or ()) > 1 and bool(chart.get("group_by_dimensions"))
    series = []
    for key, cols in groups.items():
        for metric, scores in cols.items():
            label = " · ".join(key) + (f" ({metric})" if several else "")
            series.append({"label": label, "value": _mean(scores)})
    if chart.get("chart_type") != "line":
        series.sort(key=lambda s: s["label"])
    if not any(s["value"] is not None for s in series):
        return None
    spec = {"id": "declared", "title": chart.get("title") or "", "kind": "bar" if chart.get("chart_type") == "line"
            else "hbar", "value_format": "percent" if _percent(chart) else "number",
            "series": series[:MAX_ITEMS]}
    if len(series) > MAX_ITEMS:
        spec["note"] = ctx.t("The first {count} of {total} are shown.", count=MAX_ITEMS, total=len(series))
    try:
        return svg(spec, getattr(ctx, "chart_colours", None) or DEFAULT_CHART_COLOURS,
                   decimal_separator=getattr(ctx, "decimal_separator", ".") or ".",
                   percent_format=getattr(ctx, "percent_format", "{value}%") or "{value}%")
    except ValueError:
        return None


def render_declared(charts, measurements, ctx) -> Markup:
    """The declared charts that have measures, each with its title and description."""
    parts = []
    for chart in charts or ():
        if not isinstance(chart, Mapping) or chart.get("chart_type") in SKIPPED:
            continue
        ms = _measures(chart, measurements)
        if not ms:
            continue
        drawn = _table(chart, ms, ctx) if chart.get("chart_type") == "table" else _bars(chart, ms, ctx)
        if drawn is None:
            continue
        title = f'<h4 class="declared-title">{escape(chart.get("title") or "")}</h4>' if chart.get("title") else ""
        note = f'<p class="declared-note">{escape(chart["description"])}</p>' if chart.get("description") else ""
        parts.append(f'<div class="declared-chart">{title}{note}{drawn}</div>')
    return Markup("".join(parts))
