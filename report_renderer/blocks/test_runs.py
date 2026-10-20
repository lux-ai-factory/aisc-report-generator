"""The Test runs block.

The runs of the report's selection: when they ran, against which version, their status and tools;
in full, each tool with its start, end and the name of its configuration. A configuration's settings
are never read (they may hold credentials, and the report login may not read them).
"""
from __future__ import annotations

from datetime import timedelta, timezone

from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult

from ..views import selection_of, version_suffix
from ._common import empty_result


def _when(value) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M")


def _day(value) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


class TestRunsBlock(BaseBlockRenderer):
    type_id = "test_runs"
    title = "Test runs"
    contract_version = 1
    description = "The test runs in the report's period: when they ran, the tests and their configuration."
    reads = ("engine", "platform")
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "detail": {"enum": ["summary", "full"], "title": "Detail",
                       "description": "One line per run, or each test with its start, end and configuration.",
                       "x-aisc-enum-labels": {"summary": "One line per run", "full": "Each test"}},
        },
    }
    default_options = {"detail": "summary"}

    def load(self, ctx, options):
        sel = selection_of(ctx)
        engine = ctx.data.engine
        evals = engine.evaluations(selection=sel)
        details = engine.run_details(evaluation_ids=[e["id"] for e in evals], selection=sel)
        return {"evaluations": evals, "details": details, "selection": sel}

    def _period(self, sel, t) -> tuple[str, str]:
        start = _day(sel.period_from) if sel and sel.period_from else t("the start")
        end = _day(sel.period_to - timedelta(days=1)) if sel and sel.period_to else t("today")
        return start, end

    def render(self, data, options, ctx):
        t = ctx.t
        evals = data["evaluations"]
        if not evals:
            start, end = self._period(data["selection"], t)
            return empty_result(t("No test runs between {start} and {end} for version {number}.",
                                  start=start, end=end, number=ctx.system["number"]))
        by_eval: dict[int, list] = {}
        for d in data["details"]:
            tool = {"name": d.get("display_name") or d["name"], "status": d["status"],
                    "started": _when(d.get("started_at")), "finished": _when(d.get("finished_at")),
                    "config_name": d.get("config_name") or ""}
            by_eval.setdefault(d["evaluation_id"], []).append(tool)
        runs = [{"date": _when(e["created_at"]), "short": e["pid"][:8], "status": e["status"],
                 "version": version_suffix(ctx, e.get("version_number")).strip(" ()") or
                 t("Version {number}", number=ctx.system["number"]),
                 "tools": by_eval.get(e["id"], [])} for e in evals]
        html = self.render_package_template("templates/test_runs.html.j2", runs=runs, options=options, t=t)
        return BlockResult(html=html, status="ok")
