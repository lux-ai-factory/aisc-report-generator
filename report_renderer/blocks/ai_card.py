"""The AI card block."""
from __future__ import annotations

from aisc_report_plugin_interface import BaseBlockRenderer

from ..data.vocab import TAG_CLASSES, vair_label
from ._common import empty_result, finish, ymd


class AiCardBlock(BaseBlockRenderer):
    type_id = "ai_card"
    title = "AI card"
    contract_version = 1
    description = "The AI system's card: what it is, who makes it and who uses it."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "show_components": {"type": "boolean", "title": "Show components",
                                "description": "Lists the models, datasets and other parts linked to the card."},
            "show_tags": {"type": "boolean", "title": "Show tags",
                          "description": "Lists the target system, sector, market and locality tags."},
            "show_graph_stats": {"type": "boolean", "title": "Show knowledge graph numbers",
                                 "description": "Adds the size and digest of the card's knowledge graph.",
                                 "x-aisc-more": True},
        },
    }
    default_options = {"show_components": True, "show_tags": True, "show_graph_stats": False}
    reads = ("platform", "qualification")
    choice_options = ()

    def load(self, ctx, options):
        q = ctx.data.qualification
        card = q.card()
        if card is None:
            return {"card": None}
        return {"card": card,
                "components": q.components() if options["show_components"] else [],
                "graph": q.knowledge_graph() if options["show_graph_stats"] else None,
                "newest_newer": q.newest_newer_card()}

    def render(self, data, options, ctx):
        card = data["card"]
        if card is None:
            return empty_result(ctx.t("No AI card for version {number}.", number=ctx.system["number"]))
        t = ctx.t
        vocab = ctx.data.vocab
        tags = []
        if options["show_tags"]:
            # VAIR terms are shown by their labels; the headings keep the report's own names
            for label, key in ((t("Target system"), "target_system_tags"), (t("Sector"), "sector_tags"),
                               (t("Market form"), "market_form_tags"), (t("Locality"), "locality_tags")):
                values = [vair_label(vocab, TAG_CLASSES[key], v) for v in (card.get(key) or []) if v]
                if values:
                    tags.append((label, values))
        vair = {"system_type": vair_label(vocab, "AISystem", card["system_type"]) if card.get("system_type") else None,
                "purpose": vair_label(vocab, "Purpose", card["purpose"]) if card.get("purpose") else None}
        graph = data.get("graph")
        html = self.render_package_template(
            "templates/ai_card.html.j2", card=card, vair=vair, version_description=ctx.system.get("description"),
            tags=tags, components=data.get("components") or [], show_components=options["show_components"],
            graph=graph if options["show_graph_stats"] else None,
            graph_built=ymd(graph["built_at"]) if graph else "", t=t)
        return finish(html, [], newest_newer=data["newest_newer"], t=t)
