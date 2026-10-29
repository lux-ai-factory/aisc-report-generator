"""A layout snapshot becomes one document.

Blocks render strictly in list order, each in its own <section>; a failing block becomes an error
box with a reference, the traceback only in the log. The document has one stylesheet, a running
header with the project and version, page numbers, and a table of contents above three blocks.
Optional features: chapters, an appendix, numbering, header and footer texts, a marking, the
document id line, commentary and the fingerprint. A feature's CSS is appended only when the
document uses it, so a snapshot that uses none keeps its exact output (the golden tests check this).
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import logging
import re
from datetime import timezone
from pathlib import Path

from markupsafe import Markup
from aisc_report_plugin_interface import BlockResult, richtext
from aisc_report_plugin_interface.templating import render_package_template

from . import languages, selection, structure
from . import snapshot as snapshot_schema
from . import style
from .blocks.free_text import is_placeholder
from .context import context_for
from .data.scope import NotInProject
from .errors import log_block_error, new_error_ref
from .pdf import html_to_pdf

logger = logging.getLogger("report_renderer.document")
CSS_PATH = Path(__file__).resolve().parent / "templates" / "report.css"
FEATURE_CSS_DIR = Path(__file__).resolve().parent / "templates" / "css"
#: marking value to its English label
MARKING_LABELS = style.MARKING_LABELS
DOCUMENT_MODES = ("pdf", "docx")


class NotFound(LookupError):
    """The project or its system version does not exist (or not together)."""


class InvalidSnapshot(ValueError):
    def __init__(self, problems: list):
        self.problems = problems
        super().__init__(f"{len(problems)} problems in the snapshot")


def _error_box(message: str) -> str:
    return render_package_template("report_renderer", "templates/error_box.html.j2", message=message)


def _render_block(b: dict, ctx, deps) -> dict:
    t = ctx.t
    iid, type_id = b["instance_id"], b["block_type"]
    cls = deps.registry.block(type_id)
    options = dict(b.get("options") or {})
    if cls is None:
        title = options.get("title") or type_id
        result = BlockResult(html=_error_box(t("This block type is not available on this platform.")),
                             status="error", notices=[t("Unknown block type: {type}.", type=type_id)])
    else:
        options = {**cls.full_default_options(), **options}
        title = options.get("title") or t(cls.title)
        problems = cls.options_problems(options)
        if problems:
            result = BlockResult(
                html=_error_box(t("This section could not be rendered: its options are invalid.")), status="error",
                notices=[t("Invalid options: {pointer}: {message}", pointer=p["pointer"].lstrip("/"),
                           message=p["message"]) for p in problems])
        else:
            try:
                inst = cls()
                data = inst.load(ctx, options)
                result = inst.render(data, options, ctx)
                if not isinstance(result, BlockResult):
                    raise TypeError("a block must return a BlockResult")
            except Exception:
                ref = new_error_ref()
                log_block_error(ref, iid, type_id)
                result = BlockResult(html=_error_box(t("This section could not be rendered (ref {ref}).", ref=ref)),
                                     status="error", notices=[])
    logger.info("block %s %s %s", iid, type_id, result.status)
    kind = type_id if type_id in ("chapter", "appendix") and cls is not None else None
    text = options.get("commentary") if isinstance(options, dict) else None
    written = isinstance(text, str) and text.strip() and not is_placeholder(text)
    commentary = richtext.render(text) if written else None
    page_break = bool(options.get("page_break_before")) if isinstance(options, dict) else False
    return {"instance_id": iid, "type_id": type_id, "title": title, "status": result.status,
            "notices": list(result.notices), "html": Markup(result.html), "kind": kind,
            "commentary": commentary, "commentary_position": options.get("commentary_position", "after"),
            "page_break": page_break or kind == "appendix", "omit": False}


def _unwritten(b: dict, ctx) -> dict:
    """A free text still holding the placeholder is left out; only its status stays."""
    return {"instance_id": b["instance_id"], "type_id": "free_text", "title": "", "status": "empty",
            "notices": [ctx.t("Not written yet: left out of the report.")], "html": Markup(""), "kind": None,
            "commentary": None, "commentary_position": "after", "page_break": False, "omit": True}


def _section(b: dict, ctx, deps) -> dict:
    """One block's section dict; an unwritten free text is marked omit."""
    if b.get("block_type") == "free_text":
        cls = deps.registry.block("free_text")
        if cls is not None:
            options = {**cls.full_default_options(), **dict(b.get("options") or {})}
            if not cls.options_problems(options) and is_placeholder(options.get("text")):
                return _unwritten(b, ctx)
    return _render_block(b, ctx, deps)


def _css_escape_char(ch: str) -> str:
    if ch == "\\":
        return "\\\\"
    if ch == '"':
        return '\\"'
    if ch == "<" or not ch.isprintable():
        # A CSS hex escape followed by the one space that ends it. Covers form feed, every other control
        # character, U+2028/U+2029 and invisible format characters, so nothing can end the string or the
        # <style> element.
        return f"\\{ord(ch):x} "
    return ch


def _css_string(value: str) -> str:
    """A CSS double-quoted string that shows `value` (line breaks as one space) and can never be left early."""
    v = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return '"' + "".join(_css_escape_char(ch) for ch in v) + '"'


_PLACEHOLDER = re.compile(r"\{(project|version|release|layout|date)\}")


def fill_placeholders(text: str, *, project, version, release, layout, date) -> str:
    """Fill {project}, {version}, {release}, {layout} and {date}; unknown names and lone braces stay as written."""
    values = {"project": project, "version": version, "release": release, "layout": layout, "date": date}
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)] if values[m.group(1)] is not None else ""), text)


def _page_label(template: str) -> str:
    """ "Page {page} of {pages}" as CSS content: strings around counter(page) and counter(pages)."""
    parts = []
    for piece in re.split(r"(\{page\}|\{pages\})", template):
        if piece == "{page}":
            parts.append("counter(page)")
        elif piece == "{pages}":
            parts.append("counter(pages)")
        elif piece:
            parts.append(_css_string(piece))
    return " ".join(parts)


def margin_texts(project_name: str, number: int, *, report=None, t=None, mode="preview", values=None) -> dict:
    """The texts of the page margins: top_left, top_right, bottom_left, bottom_center and the page
    label template. Shared by the PDF's @page rule and the DOCX header and footer."""
    t = t or (lambda msgid, **p: languages.translator()[0](msgid, **p))
    values = values or {}
    header = getattr(report, "header_text", None) if report is not None else None
    footer = getattr(report, "footer_text", None) if report is not None else None
    marking = getattr(report, "marking", "none") if report is not None else "none"
    show_id = getattr(report, "show_document_id", False) if report is not None else False
    out = {"top_left": fill_placeholders(header, **values) if header is not None
           else t("{project}, Version {version}", project=project_name, version=number),
           "top_right": t(MARKING_LABELS[marking]).upper() if marking in MARKING_LABELS else None,
           "bottom_left": fill_placeholders(footer, **values) if footer else None,
           "bottom_center": None,
           "page": t("Page {page} of {pages}")}
    if show_id:
        if mode in DOCUMENT_MODES:
            doc_id = getattr(report, "document_id", None) or ""
            out["bottom_center"] = t("Document {id} | Fingerprint {fingerprint}", id=doc_id[:8],
                                     fingerprint=(getattr(report, "fingerprint", "") or "")[:12])
        else:
            out["bottom_center"] = t("Preview, not a generated document")
    anchor = getattr(report, "ledger_anchor", None) if report is not None else None
    if anchor and mode in DOCUMENT_MODES:
        # what verify-ledger-export.py --anchor takes as it is printed: SEQ and the digest's first 16 digits
        line = t("Ledger entry {seq} · {digest}", seq=anchor["seq"], digest=anchor["entry_sha256"][:16])
        out["bottom_center"] = f"{out['bottom_center']} | {line}" if out["bottom_center"] else line
    return out


def page_css(project_name: str, number: int, *, report=None, t=None, mode="preview", values=None,
             accent: str | None = None) -> str:
    """The @page rule: header, footer, marking and the document id line in the margins."""
    m = margin_texts(project_name, number, report=report, t=t, mode=mode, values=values)
    boxes = [f" @top-left {{ content: {_css_string(m['top_left'])}; font-size: 9pt }}"]
    if m["top_right"]:
        colour = f"; color: {accent}" if accent and re.fullmatch(r"#[0-9a-fA-F]{6}", accent) else ""
        boxes.append(f" @top-right {{ content: {_css_string(m['top_right'])}{colour}; font-size: 9pt }}")
    if m["bottom_left"]:
        boxes.append(f" @bottom-left {{ content: {_css_string(m['bottom_left'])}; font-size: 9pt }}")
    if m["bottom_center"]:
        boxes.append(f" @bottom-center {{ content: {_css_string(m['bottom_center'])}; font-size: 9pt }}")
    boxes.append(f" @bottom-right {{ content: {_page_label(m['page'])}; font-size: 9pt }} }}")
    return "@page { size: A4; margin: 22mm 16mm 20mm 16mm;" + "".join(boxes)


def _css(project_name: str, number: int, **kw) -> Markup:
    return Markup(CSS_PATH.read_text(encoding="utf-8") + "\n" + page_css(project_name, number, **kw) + "\n")


def feature_css(names) -> str:
    """The CSS of the features a document uses, always in the same order."""
    out = ""
    for name in ("commentary", "chapters", "marking", "key_figures", "chart", "toc_pages", "numbering"):
        if name in names:
            out += (FEATURE_CSS_DIR / f"{name}.css").read_text(encoding="utf-8")
    return out


def legacy_links(blocks) -> tuple:
    """Coverage links for a snapshot without `coverage_links`: those of the first summary_coverage block."""
    for b in blocks:
        if b["block_type"] == "summary_coverage":
            return tuple((b.get("options") or {}).get("links") or ())
    return ()


def render(snapshot: dict, deps) -> dict:
    problems = snapshot_schema.validate(snapshot)
    if problems:
        raise InvalidSnapshot(problems)
    language = "en"  # reports are English only
    blocks = snapshot["blocks"]
    problems = snapshot_schema.structure_problems(blocks)
    if problems:
        raise InvalidSnapshot(problems)
    links = tuple(snapshot["coverage_links"]) if "coverage_links" in snapshot else legacy_links(blocks)
    look = snapshot.get("style")
    if look and look.get("logo"):
        deps = dataclasses.replace(deps, logo=style.logo_of(look))
    fingerprint = snapshot_schema.fingerprint(snapshot)
    document = snapshot.get("document") or {}
    mode = snapshot["mode"]
    report = {"marking": (look or {}).get("marking") or "none", "document_id": document.get("id"),
              "toc": document.get("toc") or "on", "numbering": bool(document.get("numbering", False)),
              "header_text": (look or {}).get("header_text"), "footer_text": (look or {}).get("footer_text"),
              "show_document_id": bool((look or {}).get("show_document_id", False)), "fingerprint": fingerprint,
              "ledger_anchor": document.get("ledger_anchor"), "declared_charts": snapshot.get("declared_charts"),
              "selection": selection.from_snapshot(snapshot.get("selection"))}
    try:
        ctx = context_for(snapshot["project_id"], snapshot["system_id"], deps=deps, mode=mode,
                          layout=snapshot["layout"], requested_by=snapshot.get("requested_by", ""),
                          coverage_links=links, language=language, report=report,
                          primary_color=(look or {}).get("primary_color"))
    except NotInProject:
        raise NotFound("no such system version in this project") from None

    every = [_section(b, ctx, deps) for b in blocks]  # omitted blocks still report a status
    sections = [s for s in every if not s["omit"]]
    has_cover = any(s["type_id"] == "cover" for s in sections)
    banner = None
    if ctx.newer_versions and not has_cover:
        banner = ctx.t("This report covers version {number}. Version {newer} is newer.",
                       number=ctx.system["number"], newer=max(ctx.newer_versions))
    plan = structure.plan(sections, toc=ctx.report.toc, numbering=ctx.report.numbering)
    features = set()
    if any(s["commentary"] for s in sections):
        features.add("commentary")
    if any(s["kind"] for s in sections):
        features.add("chapters")
    if ctx.report.marking != "none" and has_cover:
        features.add("marking")
    for type_id in ("key_figures", "chart"):
        if any(s["type_id"] == type_id for s in sections):
            features.add(type_id)
    if plan.toc_entries is not None and mode in DOCUMENT_MODES:
        features.add("toc_pages")
    if plan.toc_entries is not None and ctx.report.numbering:
        features.add("numbering")
    system = ctx.system
    values = {"project": ctx.project.get("name", ""), "version": system["number"], "release": system.get("version"),
              "layout": snapshot["layout"].get("name", ""),
              "date": ctx.generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d")}
    css = (_css(ctx.project.get("name", ""), system["number"], report=ctx.report, t=ctx.t, mode=mode,
                values=values, accent=(look or {}).get("accent_color") or "#FF007E")
           + Markup(style.css_overrides(look)) + Markup(feature_css(features)))
    html = render_package_template(
        "report_renderer", "templates/document.html.j2",
        title=snapshot["layout"]["name"], css=css, banner=banner, sections=sections, toc=plan.toc_entries,
        toc_after=plan.toc_after, language=language, t=ctx.t)
    statuses = [{"instance_id": s["instance_id"], "block_type": s["type_id"], "status": s["status"],
                 "notices": s["notices"]} for s in every]
    if mode == "pdf":
        pdf = html_to_pdf(html)
        return {"pdf_base64": base64.b64encode(pdf).decode("ascii"), "sha256": hashlib.sha256(pdf).hexdigest(),
                "fingerprint": fingerprint, "block_statuses": statuses}
    if mode == "docx":
        from .docx import html_to_docx

        margins = margin_texts(ctx.project.get("name", ""), system["number"], report=ctx.report, t=ctx.t, mode=mode,
                               values=values)
        data = html_to_docx(html, title=snapshot["layout"].get("name", ""), subject=ctx.project.get("name", ""),
                            language=language, look=look, t=ctx.t, margins=margins)
        return {"docx_base64": base64.b64encode(data).decode("ascii"), "sha256": hashlib.sha256(data).hexdigest(),
                "fingerprint": fingerprint, "block_statuses": statuses}
    return {"html": html, "fingerprint": fingerprint, "block_statuses": statuses}
