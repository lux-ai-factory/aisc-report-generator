"""The Results dashboard chart block.

A chart plots every version at once, so its comments are matched to the AI card version that was
current when each was written, and filtered by the report's selection like runs: the report's version,
inside its period; with other versions on, all of them, each marked with its version. A reply goes with its comment."""
from __future__ import annotations

import base64
import logging
from datetime import timezone

from markupsafe import escape
from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult

from ..errors import new_error_ref
from ..superset import ImagesDisabled
from ..views import selection_of, version_suffix

logger = logging.getLogger("report_renderer.blocks.dashboard_chart")


def _version_at(versions, when) -> int | None:
    """The number of the newest version saved at or before `when`; None before the first."""
    number = None
    for v in versions:
        if when is not None and v["created_at"] <= when:
            number = v["number"]
    return number


def _selected(comments, versions, ctx) -> list[dict]:
    """The comments the report's selection covers; replies follow their root."""
    sel = selection_of(ctx)
    for c in comments:
        c["version_number"] = _version_at(versions, c["created_at"])

    def wanted(c) -> bool:
        if not (sel and sel.other_versions) and c["version_number"] != ctx.system["number"]:
            return False
        if sel and sel.period_from and c["created_at"] < sel.period_from:
            return False
        return not (sel and sel.period_to and c["created_at"] >= sel.period_to)

    roots = {c["id"] for c in comments if c["parent_id"] is None and wanted(c)}
    by_id = {c["id"]: c for c in comments}

    def root_of(c):
        while c["parent_id"] is not None and c["parent_id"] in by_id:
            c = by_id[c["parent_id"]]
        return c["id"]

    return [c for c in comments if root_of(c) in roots]


def _tree(comments, include_replies, ctx=None):
    by_parent: dict = {}
    for c in comments:
        by_parent.setdefault(c["parent_id"], []).append(c)
    ids = {c["id"] for c in comments}

    def node(c):
        replies = [node(r) for r in by_parent.get(c["id"], [])] if include_replies else []
        when = c["created_at"]
        if when is not None and when.tzinfo is not None:
            when = when.astimezone(timezone.utc)
        return {"author": c["author_name"], "when": when.strftime("%Y-%m-%d %H:%M UTC") if when else "",
                "body": c["body"], "replies": replies,
                "version": version_suffix(ctx, c.get("version_number")).strip() if ctx is not None else ""}

    return [node(c) for c in comments if c["parent_id"] is None or c["parent_id"] not in ids]


class DashboardChartBlock(BaseBlockRenderer):
    type_id = "dashboard_chart"
    title = "Results dashboard chart"
    contract_version = 1
    description = ("Shows a results dashboard chart's comments and data. For a chart drawn in the report, "
                   "use the Chart section.")
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "chart_id": {"type": "integer", "minimum": 1, "x-aisc-reference": True, "title": "Chart",
                         "description": "Which dashboard chart."},
            "show_comments": {"type": "boolean", "title": "Show review comments",
                              "description": "Prints the review comments left on the chart."},
            "include_replies": {"type": "boolean", "title": "Include replies",
                                "description": "Also prints the replies to each comment.", "x-aisc-more": True},
            "width": {"type": "integer", "minimum": 400, "maximum": 1600, "title": "Image width",
                      "description": "Width of the chart image in pixels.", "x-aisc-more": True},
            "height": {"type": "integer", "minimum": 300, "maximum": 1200, "title": "Image height",
                       "description": "Height of the chart image in pixels.", "x-aisc-more": True},
        },
        "required": ["chart_id"],
    }
    default_options = {"show_comments": True, "include_replies": True, "width": 1200, "height": 700}
    reads = ("superset", "platform")
    choice_options = ("chart_id",)

    def load(self, ctx, options):
        chart_id = options["chart_id"]
        chart = ctx.data.superset_db.chart(chart_id=chart_id)
        if chart is None:
            return {"missing": True}
        data = {"missing": False, "chart": chart, "image": None, "disabled": False, "image_error_ref": None,
                "table": None, "comments": []}
        if options["show_comments"]:
            data["comments"] = _selected(ctx.data.superset_db.comments(chart_id=chart_id),
                                         ctx.data.platform.versions(), ctx)
        try:
            data["image"] = ctx.data.images.image(chart_id, options["width"], options["height"])
        except ImagesDisabled:
            data["disabled"] = True
        except Exception:
            ref = new_error_ref()
            logger.error("chart image %s failed, ref %s", chart_id, ref, exc_info=True)
            data["image_error_ref"] = ref
        if data["image"] is None:
            try:
                data["table"] = ctx.data.chart_data.data(chart_id)
            except Exception:
                data["table"] = None
        return data

    def render(self, data, options, ctx):
        t = ctx.t
        if data["missing"]:
            return BlockResult(html=f"<p>{escape(t('Chart not available in this project.'))}</p>", status="error")
        chart = data["chart"]
        link = None
        if ctx.data.superset_url:
            link = f"{ctx.data.superset_url.rstrip('/')}/explore/?slice_id={chart['id']}"
        image = None
        if data["image"]:
            image = "data:image/png;base64," + base64.b64encode(data["image"]).decode("ascii")
        notices = [t("This chart shows all system versions; this report covers version {number}.",
                     number=ctx.system["number"])]
        if options["show_comments"]:
            notices.append(t("Comments are matched to the version current when they were written."))
        html = self.render_package_template(
            "templates/dashboard_chart.html.j2", chart=chart, link=link, image=image, disabled=data["disabled"],
            error_ref=data["image_error_ref"], table=data["table"], show_comments=options["show_comments"],
            comments=_tree(data["comments"], options["include_replies"], ctx), t=t)
        return BlockResult(html=html, status="error" if data["image_error_ref"] else "ok", notices=notices)

    def choices(self, ctx, option_name) -> list[dict]:
        if option_name == "chart_id":
            return [{"value": c["id"], "label": c["slice_name"]} for c in ctx.data.superset_db.charts()]
        return []
