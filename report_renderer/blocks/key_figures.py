"""The Key figures block: the main numbers of the version on one page.

Each figure is read separately; a figure without data shows "n/a" with the missing source named, and
a source error makes only that tile "n/a (ref ...)". Tool tiles come from the dedicated tool
renderers' headline() of each tool's latest Done run.
"""
from __future__ import annotations

import logging
from datetime import timezone

from aisc_report_plugin_interface import BaseBlockRenderer
from aisc_report_plugin_interface.tools import headline_items

from ..coverage import STATUSES, coverage_for
from ..errors import SourceUnavailable, new_error_ref
from ..rating import BANDS
from ..views import load_answers, load_runs
from ._common import BlockResult, finish

logger = logging.getLogger("report_renderer.blocks.key_figures")
FIGURES = ["version", "risks", "objectives", "coverage", "tests", "checklists"]
FIGURE_LABELS = {"version": "Version", "risks": "Risks", "objectives": "Objectives", "coverage": "Coverage",
                 "tests": "Tests", "checklists": "Checklists"}
MAX_TOOL_ITEMS = 2


class KeyFiguresBlock(BaseBlockRenderer):
    type_id = "key_figures"
    title = "Key figures"
    contract_version = 1
    description = "The main numbers of the version on one page."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "figures": {"type": "array", "uniqueItems": True, "items": {"enum": FIGURES},
                        "title": "Figures", "description": "Which numbers to show, in this order.",
                        "x-aisc-enum-labels": dict(FIGURE_LABELS)},
            "show_tool_headlines": {"type": "boolean", "title": "Show test headlines",
                                    "description": "Adds the main numbers of each test with a dedicated renderer.",
                                    "x-aisc-more": True},
        },
    }
    default_options = {"figures": list(FIGURES), "show_tool_headlines": True}
    reads = ("platform", "qualification", "control_objectives", "engine", "controls")
    choice_options = ()

    def load(self, ctx, options):
        wanted = [f for f in FIGURES if f in options["figures"]]
        out = {"figures": {}, "tools": [], "newest": []}
        for fid in wanted:
            try:
                out["figures"][fid] = getattr(self, f"_{fid}")(ctx, options, out)
            except SourceUnavailable:
                ref = new_error_ref()
                logger.error("key figure %s: a source is unreachable, ref %s", fid, ref, exc_info=True)
                out["figures"][fid] = {"error": ref}
        return out

    # each reader returns {"value", "note"} or {"na": note}

    def _version(self, ctx, options, out):
        s = ctx.system
        created = s.get("created_at")
        if created is not None and getattr(created, "tzinfo", None) is not None:
            created = created.astimezone(timezone.utc)
        parts = [p for p in (s.get("version"), created.strftime("%Y-%m-%d") if created else None) if p]
        return {"value": ctx.t("Version {number}", number=s["number"]), "note": ", ".join(parts)}

    def _objectives_data(self, ctx, out):
        if "co" not in out:
            co = ctx.data.control_objectives
            assessment = co.assessment()
            out["co"] = None if assessment is None else {"rows": co.mappings(), "ids": co.objective_ids()}
            out["newest"].append(co.newest_newer_assessment())
        return out["co"]

    def _no_objectives(self, ctx):
        return {"na": ctx.t("No control objectives for version {number}.", number=ctx.system["number"])}

    def _risks(self, ctx, options, out):
        data = self._objectives_data(ctx, out)
        if data is None:
            return self._no_objectives(ctx)
        bands = {}
        for r in data["rows"]:
            bands.setdefault(r["risk_id"], r["band"])
        parts = []
        for name in BANDS:
            n = sum(1 for v in bands.values() if v == name)
            if n:
                parts.append(ctx.t("{label}: {value}", label=ctx.t(name), value=n))
        unrated = sum(1 for v in bands.values() if v is None)
        if unrated:
            parts.append(ctx.t("not rated: {count}", count=unrated))
        note = ctx.t("by rating: {parts}", parts=", ".join(parts)) if parts else ""
        return {"value": str(len(bands)), "note": note}

    def _objectives(self, ctx, options, out):
        data = self._objectives_data(ctx, out)
        if data is None:
            return self._no_objectives(ctx)
        ids = data["ids"]
        labels = ctx.data.objectives
        groups = {labels.get(oid, {}).get("macro") or "" for oid in ids} - {""}
        return {"value": str(len(ids)), "note": ctx.t("in {count} requirement groups", count=len(groups))}

    def _coverage(self, ctx, options, out):
        data = self._objectives_data(ctx, out)
        if data is None:
            return self._no_objectives(ctx)
        ids = data["ids"]
        coverage = coverage_for(ctx, ids, ctx.report.coverage_links)
        counts = {st: 0 for st in STATUSES}
        for cov in coverage.values():
            counts[cov.status] += 1
        with_evidence = counts["evidence"] + counts["evidence, attention"]
        note = ", ".join(ctx.t("{label}: {value}", label=ctx.t(st), value=counts[st]) for st in STATUSES[1:])
        return {"value": ctx.t("{count} of {total} objectives with evidence", count=with_evidence, total=len(ids)),
                "note": note}

    def _tests(self, ctx, options, out):
        view = load_runs(ctx, statuses=["Done"])
        out["newest"].append(ctx.data.engine.newest_newer_evaluation())
        if not view.evaluations:
            return {"na": ctx.t("No test results for version {number}.", number=ctx.system["number"])}
        tools: list[str] = []
        latest: dict[str, object] = {}
        for ev in view.evaluations:
            for rv in ev.runs:
                name = rv.tool.get("display_name") or rv.tool.get("name")
                if name and name not in tools:
                    tools.append(name)
                if name:
                    latest[name] = rv
        if options["show_tool_headlines"]:
            for name in tools:
                rv = latest[name]
                renderer = ctx.data.tools.tool_for(rv.tool)
                if renderer is None or getattr(renderer, "contract_version", 1) < 2:
                    continue
                try:
                    items = headline_items(renderer, rv.run, ctx)[:MAX_TOOL_ITEMS]   # values formatted with ctx
                except Exception:
                    ref = new_error_ref()
                    logger.error("headline of %s failed, ref %s", name, ref, exc_info=True)
                    continue
                package = type(renderer).__module__.split(".")[0]
                tt = ctx.translate_for(package)
                for item in items:
                    out["tools"].append({"label": ctx.t("{label}: {value}", label=name, value=tt(str(item.get("label", "")))),
                                         "value": str(item.get("value", "")),
                                         "note": tt(str(item["note"])) if item.get("note") else ""})
        return {"value": ctx.t("{count} evaluations", count=len(view.evaluations)), "note": ", ".join(tools)}

    def _checklists(self, ctx, options, out):
        view = load_answers(ctx)
        if not view.missing_db:
            out["newest"].append(ctx.data.controls.newest_newer_answer(newer=ctx.data.newer))
        lists = [ca for ca in view.checklists if ca.answered]
        if view.missing_db or not lists:
            return {"na": ctx.t("No control answers for version {number}.", number=ctx.system["number"])}
        answered = sum(ca.answered for ca in lists)
        total = sum(ca.total for ca in lists)
        scores = [r["score"] for ca in lists for r in ca.rows if r["answered"] and r["score"] is not None]
        note = ""
        if scores:
            note = ctx.t("mean score {mean} (1 to 5)", mean=ctx.number(round(sum(scores) / len(scores), 1)))
        return {"value": ctx.t("{answered} of {total} questions answered", answered=answered, total=total),
                "note": note}

    def render(self, data, options, ctx):
        t = ctx.t
        tiles = []
        any_value = False
        error = False
        for fid in [f for f in FIGURES if f in options["figures"]]:
            fig = data["figures"].get(fid, {})
            label = t(FIGURE_LABELS[fid])
            if "error" in fig:
                error = True
                tiles.append({"id": fid, "label": label, "value": t("n/a (ref {ref})", ref=fig["error"]), "note": ""})
            elif "na" in fig:
                tiles.append({"id": fid, "label": label, "value": t("n/a"), "note": fig["na"]})
            else:
                # the version tile names the pinned version, it is not data of it: a block whose only
                # value is the version reads as empty
                any_value = any_value or fid != "version"
                tiles.append({"id": fid, "label": label, "value": fig["value"], "note": fig.get("note", "")})
            if fid == "tests":
                for item in data["tools"]:
                    tiles.append({"id": "tool", **item})
        html = self.render_package_template("templates/key_figures.html.j2", tiles=tiles)
        if error:
            return BlockResult(html=html, status="error", notices=[])
        if not any_value:
            return BlockResult(html=html, status="empty", notices=[])
        newest = [n for n in data["newest"] if n is not None]
        return finish(html, [], newest_newer=max(newest) if newest else None, t=t)
