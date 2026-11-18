"""Draw a document from the backend's report snapshot (HTML or PDF). No database is read: every
piece of data arrives inside the snapshot. The template lives in templates/report.html.j2."""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

import cardgraph
import plots

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# the pilot's look contract: the fonts the report image ships, and the mark levels
_FONT_STACKS = {
    "inter": '"Inter", "Liberation Sans", Arial, sans-serif',
    "liberation-sans": '"Liberation Sans", Arial, sans-serif',
    "liberation-serif": '"Liberation Serif", "Times New Roman", serif',
    "roboto": '"Roboto", "Liberation Sans", Arial, sans-serif',
    "dejavu-sans": '"DejaVu Sans", Verdana, sans-serif',
    "dejavu-serif": '"DejaVu Serif", Georgia, serif',
}
_MARKING_LABELS = {
    "public": "Public",
    "internal": "Internal",
    "confidential": "Confidential",
    "strictly_confidential": "Strictly confidential",
}
_LOGO_MIMES = {"image/png", "image/jpeg", "image/svg+xml"}
LOGO_MAX_BASE64 = 1_400_000


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
    env.filters["css_text"] = _css_text
    return env


def _css_text(value: str) -> str:
    """Quote a string for a CSS `content` value, escaping quotes and slashes."""
    return Markup('"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"')


def _logo_data_uri(value) -> str:
    """The style's logo as a data URI, or '' when absent or invalid."""
    if not isinstance(value, dict):
        return ""
    mime = value.get("mime")
    data = value.get("data_base64")
    if mime not in _LOGO_MIMES or not isinstance(data, str) or not data:
        return ""
    return f"data:{mime};base64,{data[:LOGO_MAX_BASE64]}"


def _style(snapshot: dict) -> dict:
    """The snapshot's customisation, sanitised: colours reach the CSS (only
    #rrggbb passes), text is clipped, the font/marking must be known values and
    the logo is validated into a data URI — never trusted from the snapshot."""
    style = snapshot.get("style") if isinstance(snapshot.get("style"), dict) else {}

    def text(key: str, limit: int) -> str:
        value = style.get(key)
        return value.strip()[:limit] if isinstance(value, str) else ""

    def colour(key: str, default: str) -> str:
        value = style.get(key)
        return value.lower() if isinstance(value, str) and _HEX.match(value) else default

    def size(key: str, default: float) -> float:
        try:
            value = float(style.get(key))
        except (TypeError, ValueError):
            value = default
        rounded = round(min(16, max(8, value)), 1)
        return rounded if rounded != int(rounded) else int(rounded)

    try:
        report_version = max(1, int(style.get("report_version") or 1))
    except (TypeError, ValueError):
        report_version = 1

    font = style.get("font") if isinstance(style.get("font"), str) else "inter"
    marking = style.get("marking") if isinstance(style.get("marking"), str) else "none"
    return {
        "report_version": report_version,
        "report_title": text("report_title", 200),
        "subtitle": text("subtitle", 300),
        "primary_color": colour("primary_color", "#000fdf"),
        "accent_color": colour("accent_color", "#ff007e"),
        "font": font if font in _FONT_STACKS else "inter",
        "font_stack": _FONT_STACKS.get(font, _FONT_STACKS["inter"]),
        "font_size_pt": size("font_size_pt", 11),
        "header_text": text("header_text", 120),
        "footer_text": text("footer_text", 120),
        "marking": marking if marking in _MARKING_LABELS else "none",
        "marking_label": _MARKING_LABELS.get(marking, ""),
        "show_document_id": bool(style.get("show_document_id", False)),
        "document_id": text("document_id", 64),
        "fingerprint": text("fingerprint", 64),
        "logo": _logo_data_uri(style.get("logo")),
    }


def _evaluations(snapshot: dict, style: dict) -> list:
    """The evaluations with their declared charts drawn (the plugin interface's
    bar renderer; a chart with no wanted rows is left out)."""
    colours = {
        "primary": style["primary_color"],
        "text": "#000000",
        "grid": "#cccccc",
    }
    return [
        {**evaluation, "plots": plots.for_evaluation(evaluation, colours)}
        if isinstance(evaluation, dict) else evaluation
        for evaluation in snapshot.get("evaluations") or []
    ]


def _node_text(node) -> str:
    """A card graph node's human text (full text first, then its label)."""
    return (
        str(node.get("fullText") or node.get("label") or "").strip()
        if isinstance(node, dict) else ""
    )


def _ai_card(system: dict) -> dict:
    """The AI card, flattened for the template: its labelled rows (aspect →
    values), graph counts and digest. Empty on a missing/malformed card."""
    card = system.get("card") if isinstance(system.get("card"), dict) else {}
    view = card.get("view") if isinstance(card.get("view"), dict) else {}
    rows = []
    for row in view.get("rows") or []:
        if not isinstance(row, dict):
            continue
        values = [
            value
            for value in (
                _node_text(n) for n in (row.get("nodes") or []) if isinstance(n, dict)
            )
            if value
        ]
        if row.get("label") or values:
            rows.append({"label": str(row.get("label") or ""), "values": values})
    counts = view.get("counts") if isinstance(view.get("counts"), dict) else {}
    system_label = (
        (view.get("system") or {}).get("label") if isinstance(view.get("system"), dict) else ""
    )
    return {
        "system_name": system_label or system.get("name") or "",
        "rows": rows,
        "counts": {k: v for k, v in counts.items() if isinstance(v, (int, float))},
        "digest": card.get("digest") if isinstance(card.get("digest"), str) else "",
    }


def _node_term(node) -> str:
    """A card node's VAIR term (shown after the `·`), empty when it has none."""
    return str(node.get("vair") or "") if isinstance(node, dict) else ""


def _risk_chains(system: dict) -> list[dict]:
    """The AI card's expanded risk chains, as the webapp shows them: each risk
    with its source, consequence, impact, those it affects, its controls and
    the impact areas."""
    card = system.get("card") if isinstance(system.get("card"), dict) else {}
    view = card.get("view") if isinstance(card.get("view"), dict) else {}
    chains = []
    for chain in view.get("chains") or []:
        if not isinstance(chain, dict):
            continue
        impact_areas = [
            str(area.get("label") or area.get("fullText") or "")
            for area in (chain.get("areas") or [])
            if isinstance(area, dict)
        ]
        chains.append(
            {
                "risk": _node_text(chain.get("risk")),
                "risk_term": _node_term(chain.get("risk")),
                "source": _node_text(chain.get("source")),
                "source_term": _node_term(chain.get("source")),
                "consequence": _node_text(chain.get("consequence")),
                "consequence_term": _node_term(chain.get("consequence")),
                "impact": _node_text(chain.get("impact")),
                "impact_term": _node_term(chain.get("impact")),
                "stakeholder": _node_text(chain.get("stakeholder")),
                "control": _node_text(chain.get("control")),
                "control_term": _node_term(chain.get("control")),
                "follow_up": _node_text(chain.get("followUp")),
                "impact_areas": [area for area in impact_areas if area],
            }
        )
    return [chain for chain in chains if chain["risk"] or chain["source"]]


def _key_figures(snapshot: dict) -> list[dict]:
    """The cover's key figures (the pilot's key_figures block): the version,
    the card's risks, the selected objectives, the checklists (coverage /
    readiness) and the tests. Tiles with no underlying data are left out."""
    figures = []

    def mean(values: list) -> str:
        return f"{round(sum(values) / len(values))}%" if values else ""

    def add(label: str, value, note: str = "") -> None:
        if value not in (None, ""):
            figures.append({"label": label, "value": str(value), "note": note or ""})

    system = snapshot.get("system") if isinstance(snapshot.get("system"), dict) else {}
    version = system.get("version") if isinstance(system.get("version"), dict) else {}
    style = snapshot.get("style") if isinstance(snapshot.get("style"), dict) else {}
    # the cover's "Version" is the report's own, not the AI card's
    try:
        report_version = max(1, int(style.get("report_version") or 1))
    except (TypeError, ValueError):
        report_version = None
    if report_version is not None:
        note = (str(version.get("created_at"))[:10] or "") if version.get("created_at") else ""
        created = (str(version.get("number")) or "") if version.get("number") is not None else ""
        add("Version", f"v{report_version}", f"AI card {created}" if created else "")
    elif version:
        number = version.get("number")
        value = version.get("version") or (f"v{number}" if number not in (None, "") else "")
        note = (str(version.get("created_at"))[:10] or "") if version.get("created_at") else ""
        add("Version", value, note)

    card = system.get("card") if isinstance(system.get("card"), dict) else {}
    view = card.get("view") if isinstance(card.get("view"), dict) else {}
    counts = view.get("counts") if isinstance(view.get("counts"), dict) else {}
    note = (
        f"{counts.get('flagged')} flagged" if counts.get("flagged") else ""
    )
    add("Risks", counts.get("risks"), note)

    objectives = snapshot.get("objectives") if isinstance(snapshot.get("objectives"), dict) else {}
    if objectives.get("priorities") is not None:
        add("Objectives", len(objectives["priorities"]))

    controls = [c for c in (snapshot.get("controls") or []) if isinstance(c, dict)]
    if controls:
        percents = [
            c["coverage"]["percent"]
            for c in controls
            if isinstance(c.get("coverage"), dict)
            and isinstance(c["coverage"].get("percent"), (int, float))
        ]
        add("Controls", len(controls), f"coverage {mean(percents)}" if percents else "")
        readiness = [
            c["readiness"] for c in controls if isinstance(c.get("readiness"), (int, float))
        ]
        add("Readiness", mean(readiness))

    evaluations = [e for e in (snapshot.get("evaluations") or []) if isinstance(e, dict)]
    if evaluations:
        scores = [
            e["key_results"]["mean_score"]
            for e in evaluations
            if isinstance(e.get("key_results"), dict)
            and isinstance(e["key_results"].get("mean_score"), (int, float))
        ]
        add("Tests", len(evaluations), f"mean score {mean(scores)}" if scores else "")

    return figures


def _page(snapshot: dict) -> str:
    style = _style(snapshot)
    system = snapshot.get("system") if isinstance(snapshot.get("system"), dict) else {}
    raw_card = system.get("card") if isinstance(system.get("card"), dict) else {}
    colours = {"primary": style["primary_color"]}
    raw_view = raw_card.get("view") if isinstance(raw_card.get("view"), dict) else {}
    # the webapp's two-band figure when the card view is usable; otherwise the
    # plain JSON-LD graph (older snapshots)
    card_graph = cardgraph.figure_svg(raw_view, colours) or cardgraph.graph_svg(raw_card, colours)
    return _env().get_template("report.html.j2").render(
        snapshot=snapshot,
        sections=snapshot.get("sections") or [],
        style=style,
        evaluations=_evaluations(snapshot, style),
        card=_ai_card(system),
        risks=_risk_chains(system),
        key_figures=_key_figures(snapshot),
        card_graph=card_graph,
    )


def render_html(snapshot: dict) -> bytes:
    return _page(snapshot).encode("utf-8")


def render_pdf(snapshot: dict) -> bytes:
    from weasyprint import HTML

    return HTML(string=_page(snapshot)).write_pdf()
