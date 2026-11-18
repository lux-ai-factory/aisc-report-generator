"""Draw a document from the backend's report snapshot (HTML or PDF).

No database is read: every piece of data arrives inside the snapshot. The
template lives in templates/report.html.j2. ``Renderer`` holds the validated
style and the parsed card figure, and renders the page; ``render_html`` and
``render_pdf`` are thin wrappers the FastAPI app calls.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

import cardgraph
import plots
from style import ReportStyle, css_text

_TEMPLATES = Path(__file__).resolve().parent / "templates"


class Renderer:
    """The document renderer: the validated look plus the content the template gets."""

    def __init__(self, snapshot: dict) -> None:
        self.snapshot = snapshot
        self.style = ReportStyle.from_snapshot(snapshot)
        self.system = snapshot.get("system") if isinstance(snapshot.get("system"), dict) else {}
        self.card = self.system.get("card") if isinstance(self.system.get("card"), dict) else {}
        self.view = self.card.get("view") if isinstance(self.card.get("view"), dict) else {}
        self.figure = cardgraph.Figure.from_view(self.view)

    # -- content ------------------------------------------------------------

    def _env(self) -> Environment:
        env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
        env.filters["css_text"] = css_text
        return env

    def evaluations(self) -> list:
        """The evaluations with their declared charts drawn (a chart with no
        wanted rows is left out)."""
        colours = {
            "primary": self.style.primary_color,
            "text": "#000000",
            "grid": "#cccccc",
        }
        return [
            {**evaluation, "plots": plots.for_evaluation(evaluation, colours)}
            if isinstance(evaluation, dict) else evaluation
            for evaluation in self.snapshot.get("evaluations") or []
        ]

    def card_aspects(self) -> dict:
        """The AI card, flattened for the template: its labelled rows (aspect →
        values), graph counts and digest."""
        rows = []
        if self.figure is not None:
            for row in self.figure.rows:
                values = [node.text for node in row.nodes if node.text]
                if row.label or values:
                    rows.append({"label": row.label, "values": values})
        counts = self.view.get("counts") if isinstance(self.view.get("counts"), dict) else {}
        system_label = (
            self.figure.system.label
            if self.figure is not None and self.figure.system
            else ""
        )
        return {
            "system_name": system_label or self.system.get("name") or "",
            "rows": rows,
            "counts": {k: v for k, v in counts.items() if isinstance(v, (int, float))},
            "digest": self.card.get("digest") if isinstance(self.card.get("digest"), str) else "",
        }

    def risk_cards(self) -> list[dict]:
        """The AI card's expanded risk chains, as the webapp shows them: each
        risk with its source, consequence, impact, those it affects, its
        controls and the impact areas."""
        if self.figure is None:
            return []

        def node_text(node) -> str:
            return node.text if node is not None else ""

        def node_term(node) -> str:
            return node.vair or "" if node is not None else ""

        cards = []
        for chain in self.figure.chains:
            cards.append(
                {
                    "risk": node_text(chain.risk),
                    "risk_term": node_term(chain.risk),
                    "source": node_text(chain.source),
                    "source_term": node_term(chain.source),
                    "consequence": node_text(chain.consequence),
                    "consequence_term": node_term(chain.consequence),
                    "impact": node_text(chain.impact),
                    "impact_term": node_term(chain.impact),
                    "stakeholder": node_text(chain.stakeholder),
                    "control": node_text(chain.control),
                    "control_term": node_term(chain.control),
                    "follow_up": node_text(chain.follow_up),
                    "impact_areas": [area.label or area.full_text or "" for area in chain.areas],
                }
            )
        return [card for card in cards if card["risk"] or card["source"]]

    def key_figures(self) -> list[dict]:
        """The cover's key figures: the report version, the card's risks, the
        selected objectives, the checklists and the tests. Tiles with no
        underlying data are left out."""
        figures = []

        def mean(values: list) -> str:
            return f"{round(sum(values) / len(values))}%" if values else ""

        def add(label: str, value, note: str = "") -> None:
            if value not in (None, ""):
                figures.append({"label": label, "value": str(value), "note": note or ""})

        version = self.system.get("version") if isinstance(self.system.get("version"), dict) else {}
        if version:
            number = version.get("number")
            add(
                "Version",
                f"v{self.style.report_version}",
                f"AI card {number}" if number is not None else "",
            )

        counts = self.view.get("counts") if isinstance(self.view.get("counts"), dict) else {}
        flagged = f"{counts.get('flagged')} flagged" if counts.get("flagged") else ""
        add("Risks", counts.get("risks"), flagged)

        objectives = (
            self.snapshot.get("objectives")
            if isinstance(self.snapshot.get("objectives"), dict)
            else {}
        )
        if objectives.get("priorities") is not None:
            add("Objectives", len(objectives["priorities"]))

        controls = [c for c in (self.snapshot.get("controls") or []) if isinstance(c, dict)]
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

        evaluations = [
            e for e in (self.snapshot.get("evaluations") or []) if isinstance(e, dict)
        ]
        if evaluations:
            scores = [
                e["key_results"]["mean_score"]
                for e in evaluations
                if isinstance(e.get("key_results"), dict)
                and isinstance(e["key_results"].get("mean_score"), (int, float))
            ]
            add("Tests", len(evaluations), f"mean score {mean(scores)}" if scores else "")

        return figures

    def card_graph(self) -> Markup | None:
        """The webapp's two-band figure when the card view is usable; otherwise
        the plain JSON-LD graph (older snapshots)."""
        colours = {"primary": self.style.primary_color}
        return cardgraph.figure_svg(self.view, colours) or cardgraph.graph_svg(self.card, colours)

    # -- output --------------------------------------------------------------

    def page(self) -> str:
        return self._env().get_template("report.html.j2").render(
            snapshot=self.snapshot,
            sections=self.snapshot.get("sections") or [],
            style=self.style,
            evaluations=self.evaluations(),
            card=self.card_aspects(),
            risks=self.risk_cards(),
            key_figures=self.key_figures(),
            card_graph=self.card_graph(),
        )

    def render_html(self) -> bytes:
        return self.page().encode("utf-8")

    def render_pdf(self) -> bytes:
        from weasyprint import HTML

        return HTML(string=self.page()).write_pdf()


def render_html(snapshot: dict) -> bytes:
    return Renderer(snapshot).render_html()


def render_pdf(snapshot: dict) -> bytes:
    return Renderer(snapshot).render_pdf()
