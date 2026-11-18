"""Draw the AI card's knowledge graph as inline SVG for the PDF/HTML report.

Two drawings are produced, both pure functions of the snapshot (no DB, no JS):

- ``figure_svg`` — the webapp's card figure from ``system.card.view``: the system
  band (the AI system node and its aspect rows, fully expanded) and a risk band
  (one expanded chain per row), laid out with the webapp's slot tables.
- ``graph_svg`` — a fallback from the backend's normalized ``{nodes, edges}`` or
  the card's raw JSON-LD (older snapshots): nodes in BFS depth columns.

Data is parsed into small value types (``Figure`` / ``JsonLdGraph``), laid out
by separate layout classes into positioned nodes/edges/bands, and rendered by a
single ``SvgRenderer`` that scales the result to fit one printed page.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import ClassVar

from markupsafe import Markup, escape

# a graph bigger than this is skipped (the stats line already reports its size)
MAX_NODES = 150

# the drawing is scaled to fit one A4/Letter content box, never overflowing it
PAGE_WIDTH_MM = 168.0
PAGE_HEIGHT_MM = 230.0

_LOCAL = re.compile(r"[#/:]([^#/:]+)$")
_RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
_QUAL = "https://lux-ai-factory.github.io/qualification/ns#"


def _local_name(iri: str) -> str:
    match = _LOCAL.search(iri)
    return match.group(1) if match else iri


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _literal(node: dict, *keys: str) -> str | None:
    """The node's first non-empty string value for the keys (a ``@value`` is
    unwrapped), like the webapp's ``firstLiteral``."""
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item:
                    return item
                if (
                    isinstance(item, dict)
                    and isinstance(item.get("@value"), str)
                    and item["@value"]
                ):
                    return item["@value"]
    return None


# ---------------------------------------------------------------------------
# value types: the webapp's card view, and the plain JSON-LD graph


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    cls: str | None = None
    vair: str | None = None
    full_text: str | None = None

    @classmethod
    def from_view(cls, raw) -> Node | None:
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("label"):
            return None
        return cls(
            id=str(raw["id"]),
            label=str(raw["label"]),
            cls=raw.get("cls"),
            vair=raw.get("vair"),
            full_text=raw.get("fullText"),
        )

    @property
    def type_text(self) -> str:
        # the node's type: its VAIR term when it has one, else its class
        return str(self.vair or self.cls or "")


@dataclass
class Row:
    property: str
    label: str
    nodes: list[Node]


@dataclass
class Chain:
    risk: Node
    source: Node | None = None
    consequence: Node | None = None
    impact: Node | None = None
    vulnerability: Node | None = None
    control: Node | None = None
    follow_up: Node | None = None
    areas: list[Node] = field(default_factory=list)


@dataclass
class Figure:
    """The webapp's card figure: the system, its aspect rows and the risk chains."""

    system: Node
    rows: list[Row] = field(default_factory=list)
    chains: list[Chain] = field(default_factory=list)

    @classmethod
    def from_view(cls, view) -> Figure | None:
        view = view if isinstance(view, dict) else {}
        system = Node.from_view(view.get("system"))
        if system is None:
            return None
        rows = []
        for item in view.get("rows") or []:
            if not isinstance(item, dict) or not item.get("property"):
                continue
            nodes = [
                n for n in (Node.from_view(n) for n in (item.get("nodes") or []))
                if n is not None
            ]
            if not nodes:
                continue
            rows.append(
                Row(
                    property=str(item["property"]),
                    label=str(item.get("label") or item["property"]),
                    nodes=nodes,
                )
            )
        chains = []
        for item in view.get("chains") or []:
            if not isinstance(item, dict):
                continue
            risk = Node.from_view(item.get("risk"))
            if risk is None:
                continue
            chains.append(
                Chain(
                    risk=risk,
                    source=Node.from_view(item.get("source")),
                    consequence=Node.from_view(item.get("consequence")),
                    impact=Node.from_view(item.get("impact")),
                    vulnerability=Node.from_view(item.get("vulnerability")),
                    control=Node.from_view(item.get("control")),
                    follow_up=Node.from_view(item.get("followUp")),
                    areas=[
                        a for a in (Node.from_view(x) for x in (item.get("areas") or []))
                        if a is not None
                    ],
                )
            )
        return cls(system=system, rows=rows, chains=chains)


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""


@dataclass
class JsonLdGraph:
    """A plain node/edge graph, from the backend's ``card.graph`` or raw JSON-LD."""

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


def _jsonld_label(node: dict) -> str:
    label = _literal(node, _RDFS_LABEL, "rdfs:label", "label")
    if label:
        return label
    question_id = _literal(node, f"{_QUAL}questionId", "qual:questionId")
    text = _literal(node, f"{_QUAL}text", "qual:text")
    if question_id and text:
        return f"answer {question_id}: {' '.join(text.split())}"
    if question_id:
        return f"answer {question_id}"
    if text:
        return " ".join(text.split())
    node_id = str(node.get("@id") or "node")
    if node_id.startswith("_:"):
        return _literal(node, f"{_QUAL}citation", "qual:citation") or "answer"
    return _local_name(node_id)


def _jsonld_type(node: dict) -> str:
    kind = node.get("@type")
    if isinstance(kind, list):
        return ",".join(_local_name(str(item)) for item in kind if item)
    return _local_name(str(kind)) if kind else ""


def graph_from_card(card: dict) -> JsonLdGraph:
    """The drawable graph of a card: its backend-normalized ``graph`` when
    present, else parsed from the raw JSON-LD string (older snapshots)."""
    graph = card.get("graph") if isinstance(card, dict) else None
    if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
        nodes = [
            Node(id=str(n.get("id") or ""), label=str(n.get("label") or ""), cls=n.get("type"))
            for n in graph["nodes"]
            if isinstance(n, dict) and n.get("id") and n.get("label")
        ]
        edges = [
            Edge(str(e["source"]), str(e["target"]))
            for e in (graph.get("edges") or [])
            if isinstance(e, dict) and e.get("source") and e.get("target")
        ]
        return JsonLdGraph(nodes=nodes, edges=edges)

    jsonld = card.get("jsonld") if isinstance(card, dict) else None
    if not isinstance(jsonld, str):
        return JsonLdGraph()
    try:
        parsed = json.loads(jsonld)
    except ValueError:
        return JsonLdGraph()
    if isinstance(parsed, list):
        entries = [n for n in parsed if isinstance(n, dict)]
    elif isinstance(parsed, dict) and isinstance(parsed.get("@graph"), list):
        entries = [n for n in parsed["@graph"] if isinstance(n, dict)]
    elif isinstance(parsed, dict) and isinstance(parsed.get("@id"), str):
        entries = [parsed]
    else:
        entries = []

    ids = {str(n.get("@id")) for n in entries}
    nodes = [
        Node(id=str(n.get("@id") or ""), label=_jsonld_label(n), cls=_jsonld_type(n))
        for n in entries
        if n.get("@id")
    ]
    edges = []
    for node in entries:
        source = str(node.get("@id") or "")
        for key, value in node.items():
            if key.startswith("@"):
                continue
            targets = value if isinstance(value, list) else [value]
            for target in targets:
                if (
                    isinstance(target, dict)
                    and isinstance(target.get("@id"), str)
                    and target["@id"] in ids
                    and target["@id"] != source
                ):
                    edges.append(Edge(source, target["@id"], _local_name(key)))
    return JsonLdGraph(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# layout: positioned nodes, edges and bands


@dataclass
class PlacedNode:
    node: Node
    x: float
    y: float
    band: str  # "system" | "risk" | "graph"


@dataclass
class Band:
    label: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class LayoutResult:
    nodes: list[PlacedNode]
    edges: list[tuple[str, str, str]]  # (source_id, target_id, label)
    bands: list[Band]
    node_w: float
    node_h: float


class _FigureLayout:
    """The webapp's slot layout, with every row and chain fully expanded."""

    NODE_W, NODE_H = 118, 40
    COL, ROW = 150, 66
    BAND_SPLIT = 1.9 * ROW
    CHAIN_HEIGHT = 2.4 * ROW
    HOFF, VOFF = NODE_W + 24, NODE_H + 16
    PAD = 26

    # col/row slot + the direction member nodes grow (cardFigure's UPPER_SLOTS)
    UPPER_SLOTS: ClassVar[dict[str, tuple[float, float, str]]] = {
        "hasCapability": (-2, -2, "up"),
        "hasPurpose": (-1, -2, "up"),
        "isAppliedWithinDomain": (0, -2, "up"),
        "usesTechnique": (-2, -1, "left"),
        "hasModality": (-2, 0, "left"),
        "isUsedWithinLocality": (-2, 1, "left"),
        "hasComponent": (0, 1.6, "down"),
        "isProvidedBy": (2, -2, "right"),
        "isDeployedBy": (2, -1, "right"),
        "hasAIUser": (2, 0, "right"),
    }
    # each chain node's column/row inside its row (cardFigure's CHAIN_SLOTS)
    RISK_SLOTS: ClassVar[dict[str, tuple[float, float]]] = {
        "source": (-2, 0),
        "risk": (0, 0),
        "consequence": (1.6, 0),
        "impact": (3.2, 0),
        "vulnerability": (-2, 1),
        "control": (0, 1),
        "followUp": (1.6, 1),
    }
    AREA_SLOT = (1.2, 1.6)
    AREA_STEP = 0.9

    @staticmethod
    def _at(dx: float, dy: float, top: float = 0.0) -> tuple[float, float]:
        return dx * _FigureLayout.COL, top + dy * _FigureLayout.ROW

    def layout(self, figure: Figure) -> LayoutResult:
        placed: dict[str, PlacedNode] = {}
        edges: list[tuple[str, str, str]] = []

        def add(node: Node, x: float, y: float, band: str) -> None:
            if node.id not in placed:
                placed[node.id] = PlacedNode(node, x, y, band)

        def connect(source: str, target: str, label: str) -> None:
            if source in placed and target in placed:
                edges.append((source, target, label))

        def outward(away: str, step: float) -> tuple[float, float]:
            if away == "up":
                return 0.0, -step * self.VOFF
            if away == "down":
                return 0.0, step * self.VOFF
            if away == "left":
                return -step * self.HOFF, 0.0
            return step * self.HOFF, 0.0

        add(figure.system, *self._at(0, 0), "system")
        for row in figure.rows:
            slot = self.UPPER_SLOTS.get(row.property)
            if not slot:
                continue
            col, row_off, away = slot
            base_x, base_y = self._at(col, row_off)
            for index, member in enumerate(row.nodes):
                step = index if len(row.nodes) == 1 else index + 1
                dx, dy = outward(away, step)
                add(member, base_x + dx, base_y + dy, "system")
                connect(figure.system.id, member.id, _local_name(row.property))

        # the risk band starts under the system band
        system = [p for p in placed.values() if p.band == "system"]
        system_y = [p.y for p in system]
        top = max(
            self.BAND_SPLIT,
            max(system_y) + self.NODE_H - min(system_y) + 0.5 * self.ROW,
        )
        for chain in figure.chains:
            row_top = top
            top += self.CHAIN_HEIGHT

            add(chain.risk, *self._at(*self.RISK_SLOTS["risk"], row_top), "risk")
            connect(figure.system.id, chain.risk.id, "hasRisk")
            if chain.source:
                add(chain.source, *self._at(*self.RISK_SLOTS["source"], row_top), "risk")
                connect(chain.source.id, chain.risk.id, "isRiskSourceFor")
                if chain.vulnerability:
                    add(
                        chain.vulnerability,
                        *self._at(*self.RISK_SLOTS["vulnerability"], row_top),
                        "risk",
                    )
                    connect(chain.source.id, chain.vulnerability.id, "exploitsVulnerability")
            if chain.consequence:
                add(chain.consequence, *self._at(*self.RISK_SLOTS["consequence"], row_top), "risk")
                connect(chain.risk.id, chain.consequence.id, "hasConsequence")
                if chain.impact:
                    add(chain.impact, *self._at(*self.RISK_SLOTS["impact"], row_top), "risk")
                    connect(chain.consequence.id, chain.impact.id, "hasImpact")
                    for step, area in enumerate(chain.areas):
                        add(
                            area,
                            *self._at(
                                self.AREA_SLOT[0] + step * self.AREA_STEP,
                                self.AREA_SLOT[1],
                                row_top,
                            ),
                            "risk",
                        )
                        connect(chain.impact.id, area.id, "hasImpactOnArea")
            if chain.control:
                add(chain.control, *self._at(*self.RISK_SLOTS["control"], row_top), "risk")
                connect(chain.control.id, chain.risk.id, "modifiesRiskConcept")
                if chain.follow_up:
                    add(
                        chain.follow_up,
                        *self._at(*self.RISK_SLOTS["followUp"], row_top),
                        "risk",
                    )
                    connect(chain.control.id, chain.follow_up.id, "isFollowedByControl")

        def band_of(band: str, label: str) -> Band | None:
            members = [p for p in placed.values() if p.band == band]
            if not members:
                return None
            xs = [p.x for p in members]
            ys = [p.y for p in members]
            pad = self.PAD
            return Band(
                label=label,
                x=min(xs) - pad,
                y=min(ys) - pad,
                width=max(xs) + self.NODE_W - min(xs) + 2 * pad,
                height=max(ys) + self.NODE_H - min(ys) + 2 * pad,
            )

        bands = [
            b for b in (
                band_of("system", "AI system and its use"),
                band_of("risk", "Risks"),
            )
            if b is not None
        ]
        return LayoutResult(
            nodes=list(placed.values()),
            edges=edges,
            bands=bands,
            node_w=self.NODE_W,
            node_h=self.NODE_H,
        )


class _BfsLayout:
    """The JSON-LD fallback: nodes in BFS depth columns from the AISystem node."""

    NODE_W, NODE_H = 190, 48
    COL, ROW = NODE_W + 24, NODE_H + 14

    def layout(self, graph: JsonLdGraph) -> LayoutResult:
        ids = [node.id for node in graph.nodes]
        start = next(
            (
                node_id
                for node_id, node in zip(ids, graph.nodes)
                if "AISystem" in node.cls or "aisc" in node_id.lower()
            ),
            ids[0] if ids else None,
        )
        depth: dict[str, int] = {start: 0} if start is not None else {}
        queue = [start] if start is not None else []
        while queue:
            current = queue.pop(0)
            for edge in graph.edges:
                if edge.source == current and edge.target not in depth:
                    depth[edge.target] = depth[current] + 1
                    queue.append(edge.target)
        for node_id in ids:
            depth.setdefault(node_id, 0)

        per_depth: dict[int, list[str]] = {}
        for node_id in ids:
            per_depth.setdefault(depth[node_id], []).append(node_id)
        by_id = {node.id: node for node in graph.nodes}
        placed = [
            PlacedNode(by_id[node_id], level * self.COL, index * self.ROW, "graph")
            for level, layer in per_depth.items()
            for index, node_id in enumerate(layer)
        ]
        edges = [
            (edge.source, edge.target, edge.label)
            for edge in graph.edges
            if edge.source in by_id and edge.target in by_id
        ]
        return LayoutResult(
            nodes=placed,
            edges=edges,
            bands=[],
            node_w=self.NODE_W,
            node_h=self.NODE_H,
        )


# ---------------------------------------------------------------------------
# rendering


class SvgRenderer:
    """Draw a ``LayoutResult`` as one inline SVG scaled to fit a printed page."""

    PAD = 12

    def __init__(self, colours: dict) -> None:
        self.primary = escape(colours.get("primary", "#000fdf"))

    def render(self, result: LayoutResult) -> Markup:
        node_w, node_h = result.node_w, result.node_h
        parts = []
        for band in result.bands:
            parts += [
                (
                    f'<rect x="{band.x:.0f}" y="{band.y:.0f}" width="{band.width:.0f}"'
                    f' height="{band.height:.0f}" rx="8" fill="#f5f7fb" stroke="#dfe3ea"/>'
                ),
                (
                    f'<text x="{band.x + 8:.0f}" y="{band.y + 12:.0f}" font-size="9"'
                    f' font-style="italic" fill="#667085">{escape(band.label)}</text>'
                ),
            ]
        by_id = {placed.node.id: placed for placed in result.nodes}
        for source, target, label in _dedupe(result.edges):
            a = by_id[source]
            b = by_id[target]
            x1, y1 = a.x + node_w, a.y + node_h / 2
            x2, y2 = b.x, b.y + node_h / 2
            mid = (x1 + x2) / 2
            parts.append(
                f'<path d="M {x1:.0f} {y1:.0f} C {mid:.0f} {y1:.0f},'
                f' {mid:.0f} {y2:.0f}, {x2:.0f} {y2:.0f}"'
                f' fill="none" stroke="#98a2b3" stroke-width="1"/>'
            )
            if label:
                parts.append(
                    f'<text x="{mid:.0f}" y="{(y1 + y2) / 2 - 3:.0f}" text-anchor="middle"'
                    f' font-size="7.5" fill="#98a2b3">{escape(label)}</text>'
                )
        for placed in result.nodes:
            x, y = placed.x, placed.y
            label = escape(_truncate(placed.node.label, 18 if placed.band != "graph" else 34))
            sub = escape(_truncate(placed.node.type_text, 20)) if placed.node.type_text else ""
            system = "aisc" in placed.node.id.lower() or placed.node.id.startswith("hub:")
            risk = placed.band == "risk"
            fill = self.primary if system else ("#fff4e6" if risk else "#ffffff")
            stroke = self.primary if system else ("#ffb020" if risk else "#cbd5e1")
            text_colour = "#ffffff" if system else "#1f2933"
            parts.append(
                f'<g>'
                f'<rect x="{x:.0f}" y="{y:.0f}" width="{node_w:.0f}" height="{node_h:.0f}"'
                f' rx="6" fill="{fill}" stroke="{stroke}"/>'
                f'<text x="{x + node_w / 2:.0f}" y="{y + 17:.0f}" text-anchor="middle"'
                f' font-size="8.5" font-weight="bold" fill="{text_colour}">{label}</text>'
                + (
                    f'<text x="{x + node_w / 2:.0f}" y="{y + 30:.0f}" text-anchor="middle"'
                    f' font-size="8" fill="{text_colour}">{sub}</text>'
                    if sub else ""
                )
                + '</g>'
            )

        nodes = result.nodes
        min_x = (
            min(b.x for b in result.bands) - self.PAD
            if result.bands else min(p.x for p in nodes) - self.PAD
        )
        min_y = (
            min(b.y for b in result.bands) - 12
            if result.bands else min(p.y for p in nodes) - self.PAD
        )
        min_y = min(min_y, min(p.y for p in nodes) - self.PAD)
        max_x = (
            max(b.x + b.width for b in result.bands)
            if result.bands else max(p.x + node_w for p in nodes)
        )
        max_y = (
            max(b.y + b.height for b in result.bands)
            if result.bands else max(p.y + node_h for p in nodes)
        )
        w_px = max_x - min_x + self.PAD
        h_px = max_y - min_y + self.PAD
        scale = min(PAGE_WIDTH_MM / w_px, PAGE_HEIGHT_MM / h_px)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="AI system graph"'
            f' viewBox="{min_x:.0f} {min_y:.0f} {w_px:.0f} {h_px:.0f}"'
            f' preserveAspectRatio="xMidYMid meet"'
            f' width="{w_px * scale:.0f}mm" height="{h_px * scale:.0f}mm"'
            f' style="max-width:100%;height:auto">{"".join(parts)}</svg>'
        )
        return Markup(svg)


def _dedupe(edges: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Keep the first edge per (source, target) so parallel system edges don't stack."""
    seen: set[tuple[str, str]] = set()
    out = []
    for source, target, label in edges:
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        out.append((source, target, label))
    return out


# ---------------------------------------------------------------------------
# public API


def figure_svg(view: dict, colours: dict) -> Markup | None:
    """The webapp's card figure (system band + expanded risk chains) as an inline
    SVG, or None when the snapshot has no usable ``system.card.view``."""
    figure = Figure.from_view(view)
    if figure is None:
        return None
    result = _FigureLayout().layout(figure)
    if not result.nodes:
        return None
    return SvgRenderer(colours).render(result)


def graph_svg(card: dict, colours: dict) -> Markup | None:
    """The plain node/edge graph as an inline SVG, or None when the snapshot has
    no drawable graph (or it is too dense for print)."""
    graph = graph_from_card(card)
    if not graph.nodes or len(graph.nodes) > MAX_NODES:
        return None
    result = _BfsLayout().layout(graph)
    if not result.nodes:
        return None
    return SvgRenderer(colours).render(result)
