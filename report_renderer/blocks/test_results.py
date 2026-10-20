"""The Test results block.

The runs shown are the report's selection; the block's tools, targets, metrics and statuses options
narrow them.

Each run names what it tested: "Tested: Scoring model (Model, AI card v2)", "Tested: System
Example Assistant (AI card v2)", "Tested: not recorded" for a run made before targets. The `targets` option keeps
the runs whose target has one of the given keys (system, component:<id>) or labels.

Evaluations are headed by their readable name ("Evaluation 2: LangBiTe, StrongREJECT"); the meta line
keeps the short id as a reference. The block can pick metrics, and passes `show_charts` and `detail`
to the tool renderers as ctx.tool_options.
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import timezone

from markupsafe import Markup
from aisc_report_plugin_interface import BaseBlockRenderer

from .. import declared
from ..errors import new_error_ref
from ..tools.generic import render_generic
from ..views import evaluation_names, kind_label, load_runs, metric_choices, target_choices
from ._common import empty_result, finish

logger = logging.getLogger("report_renderer.blocks.test_results")
STATUSES = ["Done", "Failed", "Archived", "Pending", "Processing", "Custom"]


def _when(value) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M")


def target_line(target, t) -> str:
    """What a run assessed, in one line of plain text."""
    if target is None:
        return t("Tested: not recorded")
    if target.get("status") == "not a target":
        return t("Tested: {label}, neither the system nor a component", label=target["label"])
    version = target.get("card_version")
    if target.get("kind") == "system":
        line = t("Tested: System {label} (AI card v{version})", label=target["label"], version=version) \
            if version is not None else t("Tested: System {label}", label=target["label"])
    else:
        kind = kind_label(target.get("component_kind"))
        line = t("Tested: {label} ({kind}, AI card v{version})", label=target["label"], kind=kind, version=version) \
            if version is not None else t("Tested: {label} ({kind})", label=target["label"], kind=kind)
    if target.get("status") == "stale":
        line = t("{target}, not on the latest AI card", target=line)
    return line


class TestResultsBlock(BaseBlockRenderer):
    type_id = "test_results"
    title = "Test results"
    contract_version = 2
    description = "The tests' results for this version, one section per evaluation."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "tools": {
                "title": "Tests",
                "description": "Which tests to show.",
                "oneOf": [
                    {"const": "all"},
                    {"type": "array", "items": {"type": "string", "minLength": 1, "x-aisc-prose": False}},
                ],
            },
            "targets": {
                "title": "Systems and components",
                "description": "Which to show: the runs that tested the system or these components, named by key"
                               " (system, component:<id>) or by label.",
                "x-aisc-reference": True,
                "oneOf": [
                    {"const": "all"},
                    {"type": "array", "items": {"type": "string", "minLength": 1, "x-aisc-prose": False}},
                ],
            },
            "metrics": {
                "title": "Metrics",
                "description": "Which measurements to show.",
                "x-aisc-reference": True,
                "oneOf": [
                    {"const": "all"},
                    {"type": "array", "items": {"type": "object", "required": ["tool", "metric"],
                                                "properties": {"tool": {"type": "string"},
                                                               "metric": {"type": "string"}},
                                                "additionalProperties": False}},
                ],
            },
            "detail": {"enum": ["full", "summary"], "title": "Detail",
                       "description": "Full results, or only each test's summary and chart.",
                       "x-aisc-enum-labels": {"full": "Full results", "summary": "Summary only"}},
            "statuses": {
                "type": "array",
                "minItems": 1,
                "items": {"enum": STATUSES},
                "title": "Evaluation statuses",
                "description": "Evaluations with these statuses are shown.",
                "x-aisc-enum-labels": {s: s for s in STATUSES},
                "x-aisc-more": True,
            },
            "show_measurements": {"type": "boolean", "title": "Show measurements",
                                  "description": "Shows the measurements of tests without a dedicated renderer.",
                                  "x-aisc-more": True},
            "show_artifacts": {"type": "boolean", "title": "List artifacts",
                               "description": "Lists the files each run wrote, by name and size.",
                               "x-aisc-more": True},
            "show_charts": {"type": "boolean", "title": "Show charts",
                            "description": "Lets each test draw its charts in its section.", "x-aisc-more": True},
        },
    }
    default_options = {"tools": "all", "targets": "all", "statuses": ["Done"], "show_measurements": True,
                       "show_artifacts": False, "metrics": "all", "show_charts": True, "detail": "full"}
    reads = ("platform", "engine")
    choice_options = ("tools", "targets", "metrics")

    def load(self, ctx, options):
        names = evaluation_names(ctx)
        view = load_runs(ctx, statuses=options["statuses"],
                         tools=options["tools"], metrics=options["metrics"], names=names,
                         targets=options.get("targets", "all"))
        return {"view": view, "names": names, "newest_newer": ctx.data.engine.newest_newer_evaluation()}

    def render(self, data, options, ctx):
        view = data["view"]
        t = ctx.t
        notices: list[str] = []
        if view.unversioned:
            notices.append(t("{count} evaluations are not tied to a version and are not shown.",
                             count=view.unversioned))
        if not view.evaluations:
            r = empty_result(t("No test results for version {number}.", number=ctx.system["number"]))
            r.notices.extend(notices)
            return r
        filtered = options["metrics"] != "all"
        tool_ctx = dataclasses.replace(ctx, tool_options={"show_charts": bool(options["show_charts"]),
                                                          "detail": options["detail"]})
        evaluations = []
        for ev in view.evaluations:
            runs = []
            for rv in ev.runs:
                name = rv.tool.get("display_name") or rv.tool.get("name") or t("unknown tool")
                section = None
                empty = filtered and not rv.run.measurements
                renderer = ctx.data.tools.tool_for(rv.tool)
                # the charts the plugin declares, for the tools that use them (declared.py)
                declared_charts = declared.charts_for(ctx.report, rv.run) \
                    if options["show_charts"] and declared.uses_declared(rv.tool) else []
                drawn = declared.render_declared(declared_charts, rv.run.measurements, ctx) if declared_charts else Markup("")
                run_ctx = dataclasses.replace(tool_ctx, tool_options={**tool_ctx.tool_options, "show_charts": False}) \
                    if drawn else tool_ctx
                if empty:
                    section = None
                elif renderer is not None:
                    try:
                        section = drawn + Markup(renderer.render(rv.run, run_ctx))
                    except Exception:
                        ref = new_error_ref()
                        logger.error("tool renderer for %s failed, ref %s", name, ref, exc_info=True)
                        notices.append(t("The {tool} renderer failed (ref {ref}).", tool=name, ref=ref))
                        section = render_generic(rv.run.measurements, number=ctx.number, t=t) \
                            if options["show_measurements"] else None
                else:
                    if not drawn:
                        notice = t("No dedicated renderer for {tool}; showing raw measurements.", tool=name)
                        if notice not in notices:
                            notices.append(notice)
                    table = render_generic(rv.run.measurements, number=ctx.number, t=t) \
                        if options["show_measurements"] else None
                    section = (drawn + table) if table is not None else (drawn or None)
                runs.append({"tool": name, "components": ", ".join(f"{c['name']} ({c['component_type']})"
                                                                     for c in rv.components),
                             "target": target_line(rv.run.target, t),
                             "status": rv.status, "section": section, "no_metrics": empty,
                             "artifacts": rv.artifacts if options["show_artifacts"] else []})
            unmatched = None
            if ev.unmatched_count:
                notices.append(t("{count} observations could not be tied to a tool.", count=ev.unmatched_count))
                if options["show_measurements"] and ev.unmatched:
                    unmatched = render_generic(ev.unmatched, number=ctx.number, t=t)
            e = ev.evaluation
            number, readable = data["names"].get(e["pid"], (None, t("Evaluation {short}", short=e["pid"][:8])))
            evaluations.append({"name": readable, "short": e["pid"][:8], "status": e["status"],
                                "date": _when(e["created_at"]), "runs": runs, "unmatched": unmatched})
        html = self.render_package_template("templates/test_results.html.j2", evaluations=evaluations, t=t)
        return finish(html, notices, newest_newer=data["newest_newer"], t=t)

    def choices(self, ctx, option_name) -> list[dict]:
        if option_name == "tools":
            return ctx.data.engine.tool_choices()
        if option_name == "targets":
            return target_choices(ctx)
        if option_name == "metrics":
            return metric_choices(ctx)
        return []
