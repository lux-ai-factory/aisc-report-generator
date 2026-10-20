"""Helpers of the core tests: snapshots with the version 2 keys, the service client, reading PDFs and
DOCX files, and splitting a document into its sections.

Test infrastructure only. The renderer API these tests use:

    snapshot keys: snapshot_version, language, document {id, toc, numbering},
        coverage_links, style.{header_text, footer_text, marking, show_document_id}; mode "docx"
    document.render(snapshot, deps) -> {..., "fingerprint"} in every mode, "docx_base64" in docx mode
    built-in block types "chapter" and "appendix"; common options "commentary", "commentary_position"
    report_renderer/i18n/en.json, the one language file (English only), read when a render needs it
    context.context_for(project_id, system_id, *, deps, mode, language="en", ...) -> BlockContext with
        .language and .t(msgid, **params)
    report_service: /health has interface_version and languages; /v1/block-types items have description and new_instance_options
"""
from __future__ import annotations

import base64
import io
import re
import uuid

from conftest import IDS, need, snapshot

TOKEN = "t0ken-for-v2-tests-" + "y" * 16
H = {"X-Report-Token": TOKEN}


def iid() -> str:
    return str(uuid.uuid4())


def blk(block_type: str, instance_id: str | None = None, **options) -> dict:
    return {"instance_id": instance_id or iid(), "block_type": block_type, "options": options}


def snap(blocks, project="A", system="A_V2", mode="preview", **extra) -> dict:
    """A snapshot with any of the v2 keys given as keyword arguments (language=, document=, style=...)."""
    s = snapshot(blocks, project=project, system=system, mode=mode)
    s.update(extra)
    return s


def do_render(deps, s: dict) -> dict:
    return need("report_renderer.document", "render")(s, deps)


def service(deps):
    from fastapi.testclient import TestClient

    return TestClient(need("report_service", "create_app")(deps=deps, token=TOKEN))


# Reading documents.

def pdf_pages(result_or_b64) -> list[str]:
    from pypdf import PdfReader

    b64 = result_or_b64["pdf_base64"] if isinstance(result_or_b64, dict) else result_or_b64
    return [p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(b64))).pages]


def docx_of(result: dict):
    """The python-docx Document of a docx render result (fails the test when there is none)."""
    import docx  # python-docx, a dev dependency

    assert "docx_base64" in result, f"missing feature: mode=docx returns docx_base64 (got keys {sorted(result)})"
    return docx.Document(io.BytesIO(base64.b64decode(result["docx_base64"])))


def docx_all_text(document) -> str:
    """Every text of the body: paragraphs and table cells, in order, whitespace collapsed."""
    parts = []
    body = document.element.body
    for t in body.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
        parts.append(t.text or "")
    return " ".join(" ".join(parts).split())


def docx_xml(result: dict, part: str) -> str:
    """The raw XML of one part of the DOCX package, e.g. word/document.xml or word/settings.xml."""
    import zipfile

    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["docx_base64"]))) as z:
        names = [n for n in z.namelist() if re.fullmatch(part, n)]
        return "\n".join(z.read(n).decode("utf-8") for n in names)


# Splitting a document into its sections.

_SECTION = re.compile(r'<section class="[^"]*" id="block-([0-9a-f-]{36})".*?</section>', re.S)


def split_sections(html: str) -> tuple[str, dict[str, str]]:
    """(the document with each section replaced by a marker, {instance id: section html})."""
    sections: dict[str, str] = {}

    def repl(m):
        sections[m.group(1)] = m.group(0)
        return f"<!--SECTION {m.group(1)}-->"

    return _SECTION.sub(repl, html), sections


def body_text_nodes(html: str) -> list[str]:
    """Every non-blank text node of the HTML body, whitespace collapsed.

    Text inside an inline <svg> (a chart's labels) is left out: the DOCX export turns the drawing into a
    picture, so its labels are in the image, and the chart's data table carries them as text."""
    from bs4 import BeautifulSoup
    from bs4.element import Comment

    body = BeautifulSoup(html, "html.parser").body
    out = []
    for s in body.find_all(string=True):
        if isinstance(s, Comment) or s.parent.name in ("style", "script"):
            continue
        if s.find_parent("svg") is not None:
            continue
        t = " ".join(str(s).split())
        if t:
            out.append(t)
    return out


def ids():
    return IDS
