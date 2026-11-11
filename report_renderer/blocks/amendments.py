"""The Amendments block: the corrections made to the report's version after it was first written.

Two kinds are listed: revisions of the AI card up to the revision the report pins, and checklist
submissions that an amendment made for this version. Each row says when, what, why and for whom. A
version with no amendment prints nothing, and the block is left out of the report.
"""
from __future__ import annotations

from markupsafe import Markup
from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult


def _date(value) -> str:
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value or "")[:10]


class AmendmentsBlock(BaseBlockRenderer):
    type_id = "amendments"
    title = "Amendments"
    contract_version = 1
    description = ("The corrections of the AI card and of the checklists of this version, with reason and requester."
                   " A checklist correction not yet submitted is listed with the day it was opened.")
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "include_archived": {"type": "boolean", "title": "Include archived submissions",
                                 "description": "Also lists amendments whose submission is archived.",
                                 "x-aisc-more": True},
        },
    }
    default_options = {"include_archived": False}
    reads = ("qualification", "controls")
    choice_options = ()

    def load(self, ctx, options):
        card = ctx.data.qualification.amendments()
        checklists = ctx.data.controls.amendments(include_archived=options["include_archived"])
        return {"card": card, "checklists": checklists}

    def render(self, data, options, ctx):
        t = ctx.t
        rows = [(r["created_at"], t("AI card, revision {revision}", revision=r["revision"]), r["reason"],
                 r["requested_by"]) for r in data["card"]]
        rows += [(r["created_at"], t("{checklist}, version {version}", checklist=r["checklist"], version=r["version"]),
                  r["reason"], r["requested_by"]) for r in data["checklists"]]
        if not rows:
            return BlockResult(html="", status="empty")
        rows.sort(key=lambda r: (str(r[0]), r[1]))
        head = Markup("").join(Markup("<th>{}</th>").format(h)
                               for h in (t("Date"), t("What"), t("Reason"), t("Requested by")))
        body = Markup("").join(
            Markup("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>").format(_date(d), what, reason or "",
                                                                                  who or "")
            for d, what, reason, who in rows)
        html = Markup("<table><thead><tr>{}</tr></thead><tbody>{}</tbody></table>").format(head, body)
        return BlockResult(html=str(html), status="ok", notices=[])
