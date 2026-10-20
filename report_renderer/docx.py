"""The report as a Word document.

The DOCX is made from the same document HTML as the PDF (mode docx). The HTML body is walked in
order and written with python-docx: headings to Word heading styles, paragraphs and inline runs,
links to hyperlinks, lists, tables with a repeated bold header row, definition lists to borderless
two-column tables, pictures, inline SVG charts to PNG pictures (cairosvg), notices in italics, boxes
and commentary as shaded or bordered paragraphs, page breaks, and the table of contents as a Word
TOC field. Any other element contributes its text, so no text of the body is lost.
"""
from __future__ import annotations

import base64
import io
import logging
import re

import lxml.html
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor

from . import style as style_module

logger = logging.getLogger("report_renderer.docx")
DEFAULT_PRIMARY = "000FDF"
MAX_WIDTH = Cm(16)
MONO = "Courier New"
BLOCK_TAGS = {"p", "div", "section", "nav", "ul", "ol", "li", "table", "dl", "figure", "figcaption", "h1", "h2",
              "h3", "h4", "h5", "h6", "blockquote", "svg", "img", "thead", "tbody", "tr", "br"}
#: the order of w:pPr children (WordprocessingML schema), for inserting pBdr and shd in place
PPR_SEQ = ("w:pStyle", "w:keepNext", "w:keepLines", "w:pageBreakBefore", "w:framePr", "w:widowControl", "w:numPr",
           "w:suppressLineNumbers", "w:pBdr", "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
           "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
           "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
           "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle",
           "w:rPr", "w:sectPr", "w:pPrChange")
SHADES = {"commentary": ("F3F3F3", "border"), "error-box": ("FDECEE", None), "banner": ("FFF8DC", None)}


def _first_family(stack: str) -> str:
    return stack.split(",")[0].strip().strip('"').strip("'")


def _classes(el) -> set[str]:
    return set((el.get("class") or "").split())


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "")


_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _xml_text(text: str | None) -> str:
    """Text as Word can store it: every character XML 1.0 forbids (NUL and the other C0 controls except tab,
    LF and CR, lone surrogates, U+FFFE, U+FFFF) becomes a space."""
    return _NOT_XML.sub(" ", text or "")


def _xml_safe(text: str | None) -> str:
    """Margin text as Word can store it: characters XML forbids (form feed and the other controls) become a
    space, line breaks too, as in the PDF margin."""
    return _xml_text((text or "").replace("\r\n", " ").replace("\r", " ").replace("\n", " "))


class _Writer:
    def __init__(self, document, svgs: list[str], t):
        self.doc = document
        self.svgs = list(svgs)
        self.t = t
        self.page_break = False

    # paragraphs

    def paragraph(self, container=None, style: str | None = None, shade=None):
        container = container if container is not None else self.doc
        p = container.add_paragraph(style=style) if style else container.add_paragraph()
        if self.page_break and container is self.doc:
            p.paragraph_format.page_break_before = True
            self.page_break = False
        if shade:
            self._shade(p, *shade)
        return p

    def _shade(self, p, fill, border):
        ppr = p._p.get_or_add_pPr()
        seq = list(PPR_SEQ)
        if border:
            bdr = OxmlElement("w:pBdr")
            left = OxmlElement("w:left")
            for k, v in (("w:val", "single"), ("w:sz", "18"), ("w:space", "6"), ("w:color", "FF007E")):
                left.set(qn(k), v)
            bdr.append(left)
            ppr.insert_element_before(bdr, *seq[seq.index("w:pBdr") + 1:])
        shd = OxmlElement("w:shd")
        for k, v in (("w:val", "clear"), ("w:color", "auto"), ("w:fill", fill)):
            shd.set(qn(k), v)
        ppr.insert_element_before(shd, *seq[seq.index("w:shd") + 1:])

    # inline content

    def run(self, p, text, fmt):
        if not text:
            return
        text = _collapse(_xml_text(text))
        if not text:
            return
        r = p.add_run(text)
        self._fmt(r, fmt)
        return r

    @staticmethod
    def _fmt(r, fmt):
        if fmt.get("bold"):
            r.bold = True
        if fmt.get("italic"):
            r.italic = True
        if fmt.get("mono"):
            r.font.name = MONO

    def hyperlink(self, p, url, text, fmt):
        rid = p.part.relate_to(url, RT.HYPERLINK, is_external=True)
        link = OxmlElement("w:hyperlink")
        link.set(qn("r:id"), rid)
        r = OxmlElement("w:r")
        rpr = OxmlElement("w:rPr")
        colour = OxmlElement("w:color")
        colour.set(qn("w:val"), "0563C1")
        underline = OxmlElement("w:u")
        underline.set(qn("w:val"), "single")
        if fmt.get("bold"):
            rpr.append(OxmlElement("w:b"))
        if fmt.get("italic"):
            rpr.append(OxmlElement("w:i"))
        rpr.append(colour)
        rpr.append(underline)
        r.append(rpr)
        tel = OxmlElement("w:t")
        tel.text = _collapse(_xml_text(text))
        tel.set(qn("xml:space"), "preserve")
        r.append(tel)
        link.append(r)
        p._p.append(link)

    def link_or_text(self, p, url, text, fmt):
        """An address Word cannot store becomes plain link text, checked before any relationship
        is added, so the relationships part stays valid XML."""
        if _NOT_XML.search(url):
            self.run(p, text, fmt)
            return
        try:
            self.hyperlink(p, url, text, fmt)
        except ValueError:
            self.run(p, text, fmt)

    def inline(self, p, el, fmt):
        """The text and inline children of el (its own tail is not included)."""
        self.run(p, el.text, fmt)
        for child in el:
            if not isinstance(child.tag, str):
                self.run(p, child.tail, fmt)
                continue
            tag = child.tag.lower()
            if tag == "br":
                p.add_run().add_break()
            elif tag == "svg":
                self.svg_picture(p=p)
            elif tag == "img":
                self.image(child, p=p)
            elif tag == "a" and (child.get("href") or "").startswith(("http://", "https://", "mailto:")):
                self.link_or_text(p, child.get("href"), child.text_content(), fmt)
            else:
                sub = dict(fmt)
                if tag in ("strong", "b"):
                    sub["bold"] = True
                elif tag in ("em", "i"):
                    sub["italic"] = True
                elif tag == "code":
                    sub["mono"] = True
                if tag in BLOCK_TAGS and tag not in ("br",):
                    # a block inside inline content: keep its text
                    self.run(p, " " + child.text_content() + " ", sub)
                else:
                    self.inline(p, child, sub)
            self.run(p, child.tail, fmt)

    # pictures

    def _picture(self, data: bytes, p=None):
        from PIL import Image  # python-docx needs no PIL; sizes are read cheaply if available

        width = None
        try:
            with Image.open(io.BytesIO(data)) as im:
                dpi = (im.info.get("dpi") or (96, 96))[0] or 96
                width = Emu(int(im.width / float(dpi) * 914400))
        except Exception:  # noqa: BLE001 - the width is only a hint
            width = None
        if width is None or width > MAX_WIDTH:
            width = MAX_WIDTH
        target = p if p is not None else self.paragraph()
        target.add_run().add_picture(io.BytesIO(data), width=width)

    def skip_svgs(self, el) -> None:
        """Take the SVGs of an element flattened to text off the queue: the SVGs are handed out in
        document order, so one left on it would put every later chart under the wrong heading."""
        count = sum(1 for _ in el.iter("svg"))
        del self.svgs[:count]

    def svg_picture(self, p=None) -> bool:
        source = self.svgs.pop(0) if self.svgs else ""
        try:
            import cairosvg

            data = source.encode("utf-8")
            png = cairosvg.svg2png(bytestring=data, scale=style_module.svg_raster_scale(data))
            self._picture(png, p=p)
            return True
        except Exception:  # noqa: BLE001 - the chart's table stays, with a notice
            logger.warning("an SVG could not be converted for the DOCX", exc_info=True)
            q = p if p is not None else self.paragraph()
            r = q.add_run(_xml_text(self.t("Chart shown as a table.")))
            r.italic = True
            return False

    def image(self, el, p=None):
        src = el.get("src") or ""
        m = re.match(r"data:(image/(?:png|jpeg|svg\+xml));base64,(.*)$", src, re.S)
        if not m:
            if el.get("alt"):
                self.run(p or self.paragraph(), el.get("alt"), {})
            return
        data = base64.b64decode(m.group(2))
        if m.group(1) == "image/svg+xml":
            try:
                import cairosvg

                data = cairosvg.svg2png(bytestring=data, scale=style_module.svg_raster_scale(data))
            except Exception:  # noqa: BLE001
                if el.get("alt"):
                    self.run(p or self.paragraph(), el.get("alt"), {})
                return
        try:
            self._picture(data, p=p)
        except Exception:  # noqa: BLE001
            logger.warning("a picture could not be added to the DOCX", exc_info=True)

    # blocks

    def has_blocks(self, el) -> bool:
        return any(isinstance(c.tag, str) and c.tag.lower() in BLOCK_TAGS - {"br"} for c in el)

    def children(self, el, shade=None, italic=False):
        """Block children in order; loose text and inline elements between them become paragraphs."""
        pending: list = []
        lead = el.text

        def flush():
            nonlocal lead
            texts = [lead] + [x for x in pending]
            if not any((x if isinstance(x, str) else x.text_content()).strip() for x in texts if x is not None):
                pending.clear()
                lead = None
                return
            p = self.paragraph(shade=shade)
            fmt = {"italic": italic}
            if lead:
                self.run(p, lead, fmt)
            for x in pending:
                if isinstance(x, str):
                    self.run(p, x, fmt)
                else:
                    holder = lxml.html.Element("span")
                    holder.append(_copy(x))
                    self.inline(p, holder, fmt)
            pending.clear()
            lead = None

        for child in el:
            if not isinstance(child.tag, str):
                if child.tail:
                    pending.append(child.tail)
                continue
            tag = child.tag.lower()
            if tag in BLOCK_TAGS and tag != "br":
                flush()
                self.block(child, shade=shade, italic=italic)
                if child.tail and child.tail.strip():
                    pending.append(child.tail)
            else:
                pending.append(child)
                if child.tail:
                    pending.append(child.tail)
        flush()

    def block(self, el, shade=None, italic=False, level=0):
        tag = el.tag.lower()
        cls = _classes(el)
        if "break-before: page" in (el.get("style") or ""):
            self.page_break = True
        for name, value in SHADES.items():
            if name in cls:
                shade = value
        if tag == "nav" and el.get("id") == "toc":
            return self.toc(el)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if tag == "h1":
                style = "Heading 1" if "chapter-title" in cls else "Title"
            else:
                style = {"h2": "Heading 2", "h3": "Heading 3"}.get(tag, "Heading 4")
            p = self.paragraph(style=style)
            self.inline(p, el, {})
            return
        if tag in ("ul", "ol"):
            return self.list(el, ordered=(tag == "ol"), level=level, italic=italic or "notices" in cls, shade=shade)
        if tag == "table":
            return self.table(el)
        if tag == "dl":
            return self.definitions(el)
        if tag == "svg":
            return self.svg_picture()
        if tag == "img":
            return self.image(el)
        if tag == "figcaption":
            p = self.paragraph(shade=shade)
            self.inline(p, el, {"italic": True})
            return
        if tag == "p":
            if self.has_blocks(el):
                return self.children(el, shade=shade, italic=italic)
            p = self.paragraph(shade=shade)
            self.inline(p, el, {"italic": italic})
            return
        # section, div, figure, blockquote and anything else: their children, in order
        if self.has_blocks(el):
            return self.children(el, shade=shade, italic=italic)
        if el.text_content().strip():
            p = self.paragraph(shade=shade)
            self.inline(p, el, {"italic": italic})

    def list(self, el, *, ordered, level, italic, shade):
        base = "List Number" if ordered else "List Bullet"
        style = base if level == 0 else f"{base} {min(level + 1, 3)}"
        for li in el:
            if not isinstance(li.tag, str) or li.tag.lower() != "li":
                if isinstance(li.tag, str) and li.text_content().strip():
                    p = self.paragraph(shade=shade)
                    self.inline(p, li, {"italic": italic})
                continue
            if italic:
                p = self.paragraph(shade=shade)
            else:
                p = self.paragraph(style=style, shade=shade)
            fmt = {"italic": italic}
            self.run(p, li.text, fmt)
            for child in li:
                if not isinstance(child.tag, str):
                    self.run(p, child.tail, fmt)
                    continue
                t = child.tag.lower()
                if t in ("ul", "ol"):
                    self.list(child, ordered=(t == "ol"), level=level + 1, italic=italic, shade=shade)
                elif t in BLOCK_TAGS and t != "br":
                    self.skip_svgs(child)                               # flattened: its charts are not drawn
                    holder = lxml.html.Element("span")
                    holder.text = _xml_text(child.text_content())
                    self.inline(p, holder, fmt)
                else:
                    holder = lxml.html.Element("span")
                    holder.append(_copy(child))
                    self.inline(p, holder, fmt)
                self.run(p, child.tail, fmt)

    def _cell_text(self, cell, el, bold=False):
        p = cell.paragraphs[0]
        if self.has_blocks(el):
            self.skip_svgs(el)                                          # flattened: its charts are not drawn
            holder = lxml.html.Element("span")
            holder.text = _xml_text(el.text_content())
            self.inline(p, holder, {"bold": bold})
        else:
            self.inline(p, el, {"bold": bold})

    def table(self, el):
        rows = [tr for tr in el.iter("tr")]
        if not rows:
            return
        width = max(len([c for c in tr if isinstance(c.tag, str) and c.tag.lower() in ("td", "th")]) for tr in rows)
        if width == 0:
            return
        if self.page_break:
            self.paragraph()
        table = self.doc.add_table(rows=0, cols=width)
        try:
            table.style = "Table Grid"
        except Exception:  # noqa: BLE001
            pass
        for i, tr in enumerate(rows):
            cells_el = [c for c in tr if isinstance(c.tag, str) and c.tag.lower() in ("td", "th")]
            row = table.add_row()
            header = i == 0 and (all(c.tag.lower() == "th" for c in cells_el) or tr.getparent().tag.lower() == "thead")
            for j, c in enumerate(cells_el[:width]):
                self._cell_text(row.cells[j], c, bold=header)
            if header:
                trpr = row._tr.get_or_add_trPr()
                trpr.append(OxmlElement("w:tblHeader"))

    def definitions(self, el):
        pairs, current = [], None
        for child in el:
            if not isinstance(child.tag, str):
                continue
            tag = child.tag.lower()
            if tag == "dt":
                current = [child, None]
                pairs.append(current)
            elif tag == "dd":
                if current is None or current[1] is not None:
                    current = [None, child]
                    pairs.append(current)
                else:
                    current[1] = child
        if not pairs:
            return
        if self.page_break:
            self.paragraph()
        table = self.doc.add_table(rows=0, cols=2)
        for dt, dd in pairs:
            row = table.add_row()
            if dt is not None:
                self._cell_text(row.cells[0], dt, bold=True)
            if dd is not None:
                self._cell_text(row.cells[1], dd)

    def toc(self, nav):
        heading = nav.find("h2")
        if heading is not None:
            p = self.paragraph(style="TOC Heading" if "TOC Heading" in [s.name for s in self.doc.styles] else None)
            self.inline(p, heading, {"bold": True})
        entries = []
        for a in nav.iter("a"):
            depth = sum(1 for anc in a.iterancestors() if isinstance(anc.tag, str) and anc.tag.lower() == "ol") - 1
            entries.append((max(depth, 0), _collapse(_xml_text(a.text_content())).strip()))
        if not entries:
            return
        paragraphs = []
        for depth, text in entries:
            p = self.paragraph()
            if depth:
                p.paragraph_format.left_indent = Cm(0.6 * depth)
            paragraphs.append((p, text))
        first, last = paragraphs[0][0], paragraphs[-1][0]
        _field_char(first, "begin")
        _instr(first, ' TOC \\o "1-2" \\h \\z \\u ')
        _field_char(first, "separate")
        for p, text in paragraphs:
            p.add_run(text)
        _field_char(last, "end")


def _copy(el):
    return lxml.html.fromstring(lxml.html.tostring(el, encoding="unicode", with_tail=False))


def _field_char(p, kind):
    r = OxmlElement("w:r")
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), kind)
    r.append(fc)
    p._p.append(r)


def _instr(p, text):
    r = OxmlElement("w:r")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = text
    r.append(it)
    p._p.append(r)


def _field(p, code, placeholder):
    _field_char(p, "begin")
    _instr(p, f" {code} ")
    _field_char(p, "separate")
    p.add_run(placeholder)
    _field_char(p, "end")


def _styles(document, look):
    primary = DEFAULT_PRIMARY
    normal = document.styles["Normal"].font
    if look:
        stack = next((f["stack"] for f in style_module.FONTS if f["id"] == look.get("font")), None)
        if stack:
            normal.name = _first_family(stack)
        if look.get("font_size_pt"):
            normal.size = Pt(float(look["font_size_pt"]))
        if re.fullmatch(r"#[0-9a-fA-F]{6}", look.get("primary_color") or ""):
            primary = look["primary_color"][1:].upper()
    for name in ("Title", "Heading 1", "Heading 2", "Heading 3", "Heading 4"):
        try:
            document.styles[name].font.color.rgb = RGBColor.from_string(primary)
            if look and normal.name:
                document.styles[name].font.name = normal.name
        except KeyError:
            pass


def _margins(document, margins: dict, t):
    margins = {k: (_xml_safe(v) if isinstance(v, str) else v) for k, v in margins.items()}
    section = document.sections[0]
    head = section.header.paragraphs[0]
    head.text = margins.get("top_left") or ""
    if margins.get("top_right"):
        head.add_run("\t" + margins["top_right"]).bold = True
    foot = section.footer.paragraphs[0]
    lines = [x for x in (margins.get("bottom_left"), margins.get("bottom_center")) if x]
    foot.text = "    ".join(lines)
    page = section.footer.add_paragraph()
    template = margins.get("page") or "Page {page} of {pages}"
    for piece in re.split(r"(\{page\}|\{pages\})", template):
        if piece == "{page}":
            _field(page, "PAGE", "1")
        elif piece == "{pages}":
            _field(page, "NUMPAGES", "1")
        elif piece:
            page.add_run(_xml_text(piece))


def html_to_docx(html: str, *, title: str, subject: str, language: str, look: dict | None, t,
                 margins: dict | None = None) -> bytes:
    """The document HTML (built in docx mode) as DOCX bytes."""
    html = _xml_text(html)  # also keeps chart labels drawable by cairosvg
    svgs = re.findall(r"<svg\b.*?</svg>", html, flags=re.S | re.I)
    tree = lxml.html.document_fromstring(html)
    document = Document()
    _styles(document, look)
    writer = _Writer(document, svgs, t)
    body = tree.body
    writer.children(body)
    _margins(document, margins or {}, t)
    settings = document.settings.element
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    settings.append(update)
    props = document.core_properties
    props.title = _xml_safe(title)
    props.subject = _xml_safe(subject)
    props.language = language or "en"
    props.author = ""
    props.last_modified_by = ""
    props.comments = ""
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()
