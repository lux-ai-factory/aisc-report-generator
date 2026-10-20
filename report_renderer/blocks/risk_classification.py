"""The Risk classification block."""
from __future__ import annotations

import json

from aisc_report_plugin_interface import BaseBlockRenderer

from ..data.vocab import vair_label
from ._common import empty_result, finish

#: A risk field with a VAIR term beside it, and the term's class.
RISK_TERMS = (("source", "RiskSource"), ("consequence", "Consequence"), ("impact", "Impact"),
              ("control", "RiskControl"), ("follow_up_control", "RiskControl"))

AIRO = "https://w3id.org/airo#"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
ROLES = (("provider", AIRO + "isProvidedBy"), ("deployer", AIRO + "isDeployedBy"), ("user", AIRO + "hasAIUser"))
#: the AI Act risk classes the editor may state, with the labels the composer shows and the report prints
CLASS_LABELS = {"not_determined": "Not determined", "prohibited": "Prohibited", "high": "High", "limited": "Limited",
                "minimal": "Minimal"}


def _expand(term, context) -> str:
    """A `prefix:term` key or type, expanded with the document's @context when it maps the prefix."""
    if not isinstance(term, str) or ":" not in term or "://" in term:
        return term
    prefix, rest = term.split(":", 1)
    base = context.get(prefix) if isinstance(context, dict) else None
    if isinstance(base, dict):
        base = base.get("@id")
    return base + rest if isinstance(base, str) else term


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _label(value):
    if isinstance(value, dict):
        value = value.get("@value")
    return value if isinstance(value, str) and value else None


def operators(jsonld: str | None) -> list[tuple[str, str]]:
    """(role, name) pairs from the card's JSON-LD; malformed JSON-LD gives none."""
    if not jsonld:
        return []
    try:
        doc = json.loads(jsonld)
    except (ValueError, TypeError):
        return []
    context = doc.get("@context", {}) if isinstance(doc, dict) else {}
    if isinstance(doc, dict) and isinstance(doc.get("@graph"), list):
        nodes = doc["@graph"]
    elif isinstance(doc, list):
        nodes = doc
    else:
        nodes = [doc]
    expanded = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        expanded.append({_expand(k, context): v for k, v in n.items()})
    labels = {}
    for n in expanded:
        label = None
        for v in _as_list(n.get(RDFS_LABEL)):
            label = label or _label(v)
        if isinstance(n.get("@id"), str) and label:
            labels[n["@id"]] = label
    out = []
    for n in expanded:
        types = [_expand(t, context) for t in _as_list(n.get("@type"))]
        if AIRO + "AISystem" not in types:
            continue
        for role, prop in ROLES:
            for v in _as_list(n.get(prop)):
                iri = v.get("@id") if isinstance(v, dict) else v
                if isinstance(iri, str) and iri:
                    out.append((role, labels.get(iri, iri)))
    return out


class RiskClassificationBlock(BaseBlockRenderer):
    type_id = "risk_classification"
    title = "Risk classification"
    contract_version = 1
    description = "The operators, the stated AI Act risk class and the risks of the AI card."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "stated_risk_class": {"enum": list(CLASS_LABELS),
                                  "title": "AI Act risk class",
                                  "description": "The class you state; the qualification does not classify risk.",
                                  "x-aisc-enum-labels": dict(CLASS_LABELS)},
            "show_chains": {"type": "boolean", "title": "Show risks",
                            "description": "Lists each risk with its source, consequence and controls."},
            "show_impact_areas": {"type": "boolean", "title": "Show impact areas",
                                  "description": "Adds the impact areas of each risk.", "x-aisc-more": True},
        },
    }
    default_options = {"show_chains": True, "show_impact_areas": True, "stated_risk_class": "not_determined"}
    reads = ("platform", "qualification")
    choice_options = ()

    def load(self, ctx, options):
        q = ctx.data.qualification
        card = q.card()
        if card is None:
            return {"card": None, "graph": None, "risks": [], "newest_newer": None}
        return {"card": card, "graph": q.knowledge_graph(), "risks": q.risks() if options["show_chains"] else [],
                "newest_newer": q.newest_newer_card()}

    def render(self, data, options, ctx):
        stated = options["stated_risk_class"]
        ops = operators(data["graph"]["jsonld"]) if data.get("graph") else []
        chains = data.get("risks") or []
        t = ctx.t
        number = ctx.system["number"]
        if data["card"] is None and stated == "not_determined":
            return empty_result(t("No AI card for version {number}.", number=number))
        if not ops and not chains and stated == "not_determined":
            return empty_result(t("No risk classification for version {number}.", number=number))
        if stated == "not_determined":
            risk_class = t("Not determined")
        else:
            risk_class = t("{risk_class} (stated by the report editor; the qualification does not classify risk)",
                           risk_class=t(CLASS_LABELS[stated]))
        vocab = ctx.data.vocab
        rows = []
        for r in chains:
            rows.append({**r, "affected_label": vocab["affected"].get(r["affected"], r["affected"]),
                         "impact_labels": [vocab["impactArea"].get(a, a) for a in (r.get("impact_areas") or [])],
                         # each field's VAIR term by its label; None on a card without terms
                         **{f"{f}_label": vair_label(vocab, cls, r[f"{f}_term"]) if r.get(f"{f}_term") else None
                            for f, cls in RISK_TERMS}})
        html = self.render_package_template(
            "templates/risk_classification.html.j2", operators=ops, risk_class=risk_class, chains=rows,
            show_chains=options["show_chains"], show_impact_areas=options["show_impact_areas"],
            no_card=(t("No AI card for version {number}.", number=number) if data["card"] is None else None),
            t=t)
        return finish(html, [], newest_newer=data["newest_newer"], t=t)
