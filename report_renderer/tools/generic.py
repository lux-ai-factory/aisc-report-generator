"""The generic table of a run's measurements, for tools without a renderer."""
from __future__ import annotations

from markupsafe import Markup
from aisc_report_plugin_interface.i18n import fill
from aisc_report_plugin_interface.templating import render_package_template


def _value(score) -> str:
    if score is None:
        return ""
    try:
        return f"{float(score):g}"
    except (TypeError, ValueError):
        return str(score)


def _english(msgid, **params) -> str:
    return fill(msgid, params)


def render_generic(measurements, limit=500, number=None, t=None) -> Markup:
    """number: the report's number formatter (ctx.number); t: its translator. Both default to plain English."""
    number = number or (lambda text: text)
    rows = [{"metric": m.get("metric") or m.get("name"), "value": number(_value(m.get("score"))),
             "unit": m.get("unit") or ""} for m in list(measurements)[:limit]]
    more = max(0, len(measurements) - limit)
    return Markup(render_package_template("report_renderer", "tools/templates/generic.html.j2", rows=rows, more=more,
                                          t=t or _english))
