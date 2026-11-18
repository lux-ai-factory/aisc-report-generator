"""The charts an evaluation's plugins declare (`get_metric_visualizations`).

The backend puts each plugin's declared chart specs and the run's measurements in
the snapshot; this module turns a spec into the inline SVG the renderer draws
(`charts`, the report's own bar/hbar renderer in `charts.py`).
"""
from __future__ import annotations

from markupsafe import Markup

from charts import MAX_ITEMS, svg

#: chart types the interface cannot draw (no report form)
SKIPPED = frozenset({"radar", "scatter", "kde", "csv"})
DEFAULT_COLOURS = {"primary": "#000FDF", "text": "#000000", "grid": "#CCCCCC"}


def _score(row: dict) -> float | None:
    value = row.get("score")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _mean(values: list[float | None]) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _dims(row: dict) -> dict:
    dims = row.get("dimensions")
    return dims if isinstance(dims, dict) else {}


def _rows(chart: dict, measurements: list) -> list[dict]:
    """The run's rows of the chart's metrics that pass its filter dimensions."""
    metrics = set(chart.get("metrics") or ())
    wanted = chart.get("filter_dimensions") or {}
    rows = []
    for row in measurements:
        if not isinstance(row, dict) or row.get("metric") not in metrics:
            continue
        dims = _dims(row)
        if any(dims.get(key) not in values for key, values in wanted.items()):
            continue
        rows.append(row)
    return rows


def _series(chart: dict, rows: list[dict]) -> list[dict]:
    """One bar per group (or per metric): the mean score of its rows."""
    by = list(chart.get("group_by_dimensions") or ())
    label_dim = chart.get("metric_label_dimension")
    several = len(chart.get("metrics") or ()) > 1 and bool(by)
    groups: dict[tuple, dict[str, list[float | None]]] = {}
    for row in rows:
        dims = _dims(row)
        metric = row.get("metric") or ""
        if by:
            key = tuple(str(dims.get(k, "")) for k in by)
        elif label_dim:
            key = (str(dims.get(label_dim, metric)),)
        else:
            key = (str(metric),)
        groups.setdefault(key, {}).setdefault(metric, []).append(_score(row))
    series = []
    for key, columns in groups.items():
        for metric, scores in columns.items():
            label = " · ".join(key) + (f" ({metric})" if several else "")
            series.append({"label": label, "value": _mean(scores)})
    if chart.get("chart_type") != "line":
        series.sort(key=lambda item: item["label"])
    return series


def _svg(chart: dict, rows: list[dict], colours: dict) -> Markup | None:
    series = _series(chart, rows)
    if not any(item["value"] is not None for item in series):
        return None
    spec = {
        "id": "declared",
        "title": chart.get("title") or "",
        # a line has no report form: its groups are drawn as bars, like the pilot
        "kind": "bar" if chart.get("chart_type") == "line" else "hbar",
        "value_format": "number",
        "series": series[: MAX_ITEMS],
    }
    try:
        return svg(spec, colours)
    except (ValueError, TypeError):
        return None


def for_evaluation(evaluation: dict, colours: dict | None = None) -> list[dict]:
    """The plugins' drawable charts for one evaluation: title, description, svg."""
    colours = colours or DEFAULT_COLOURS
    drawn = []
    for plugin in evaluation.get("visualizations") or ():
        if not isinstance(plugin, dict):
            continue
        measurements = plugin.get("measurements") or []
        for chart in plugin.get("charts") or ():
            if not isinstance(chart, dict) or chart.get("chart_type") in SKIPPED:
                continue
            if chart.get("chart_type") == "table":
                continue  # the key-results table already lists the metrics
            rows = _rows(chart, measurements)
            if not rows:
                continue
            svg = _svg(chart, rows, colours)
            if svg is None:
                continue
            drawn.append(
                {
                    "title": chart.get("title") or "",
                    "description": chart.get("description") or "",
                    "svg": svg,
                }
            )
    return drawn
