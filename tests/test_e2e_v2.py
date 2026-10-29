"""End to end through the renderer service.

Mike v2 (the three Example Assistant tools), a layout with chapters, an appendix, numbering, commentary, and the
key figures, chart and changes since blocks; the snapshot keeps language "fr" to prove it renders
English; rendered as preview, PDF and DOCX through
report_service.create_app with the bed's data. (The composer-to-renderer subprocess e2e is in the
composer's tests.)
"""
import base64
import io

import pytest

from conftest import soup, text
from v2_core_helpers import H, blk, service, snap

pytestmark = [pytest.mark.db]


def layout():
    return [
        blk("cover", report_title="Rapport Example Assistant"),
        blk("key_figures"),
        blk("chapter", title="Tests", intro="Les outils de test."),
        blk("test_results", commentary="Trois outils ont tourné."),
        blk("chart", dataset="checklist_scores"),
        blk("chapter", title="Versions"),
        blk("changes_since"),
        blk("appendix"),
        blk("control_answers", commentary="Réponses complètes."),
    ]


def e2e_snapshot(mode):
    blocks = layout()
    for i, b in enumerate(blocks):
        b["instance_id"] = f"00000000-0000-4000-8000-0000000e2e{i:02d}"
    return snap(blocks, project="M", system="M_V2", mode=mode,
                document={"id": "3c9d1f2e-7a6b-4c5d-8e9f-0a1b2c3d4e5f", "toc": "on", "numbering": True},
                coverage_links=[{"objective_id": "R1.1", "tests": ["LangBiTe"], "checklists": ["cl-m1"]}],
                style={"font": "inter", "font_size_pt": 10, "primary_color": "#000fdf", "accent_color": "#ff007e",
                       "marking": "internal", "show_document_id": True})


@pytest.fixture
def client(deps):
    return service(deps)


def post(client, mode):
    r = client.post("/v1/render", headers=H, json=e2e_snapshot(mode))
    assert r.status_code == 200, r.text[:800]
    return r.json()


def test_e2e_v2_preview_pdf_and_docx(client):
    preview, pdf, docx_r = post(client, "preview"), post(client, "pdf"), post(client, "docx")
    order = [b["block_type"] for b in layout()]
    for result in (preview, pdf, docx_r):
        assert [s["block_type"] for s in result["block_statuses"]] == order
        assert all(s["status"] != "error" for s in result["block_statuses"]), result["block_statuses"]
    # one content, three formats: the same fingerprint
    assert preview["fingerprint"] == pdf["fingerprint"] == docx_r["fingerprint"]

    doc = soup(preview["html"])
    assert doc.html.get("lang") == "en"                          # "fr" renders English
    heads = {s["instance_id"]: text(doc.find(id=f"block-{s['instance_id']}").find(["h1", "h2"]))
             for s in preview["block_statuses"] if s["block_type"] != "cover"}
    ids = [s["instance_id"] for s in preview["block_statuses"]]
    assert heads[ids[1]].startswith("1 ")          # key figures
    assert heads[ids[2]] == "2 Tests"               # chapter
    assert heads[ids[3]].startswith("2.1 ")         # test results inside the chapter
    assert heads[ids[4]].startswith("2.2 ")
    assert heads[ids[5]] == "3 Versions"
    assert heads[ids[6]].startswith("3.1 ")
    assert heads[ids[8]].startswith("A ")           # the appendix part
    assert text(doc.find(id="toc").find("h2")) == "Contents"
    assert "Trois outils ont tourné." in text(doc.find(id=f"block-{ids[3]}").find(class_="commentary"))
    tests_text = text(doc.find(id=f"block-{ids[3]}"))
    for tool in ("LangBiTe", "StrongREJECT", "Promptfoo"):
        assert tool in tests_text                   # a dedicated section or the generic table names it
    import importlib.util
    renderers = ("aisc_report_plugin_langbite", "aisc_report_plugin_strongreject", "aisc_report_plugin_promptfoo")
    if all(importlib.util.find_spec(m) for m in renderers):
        assert "No dedicated renderer" not in tests_text
    else:                                           # optional renderers absent: the generic table is shown
        assert "No dedicated renderer" in tests_text
    assert "HARMFULPROMPTCONTENT" not in preview["html"]
    # version 1 data only inside the comparison block
    outside = [text(doc.find(id=f"block-{i}")) for i in ids if i != ids[6]]
    assert not any("M1MARK" in t for t in outside)

    raw_pdf = base64.b64decode(pdf["pdf_base64"])
    assert raw_pdf[:5] == b"%PDF-"
    from pypdf import PdfReader

    full = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(raw_pdf)).pages)
    assert "INTERNAL" in full.upper() and "INTERNE " not in full.upper()
    assert "3c9d1f2e" in full                       # the document id line

    import docx

    d = docx.Document(io.BytesIO(base64.b64decode(docx_r["docx_base64"])))
    assert d.core_properties.language == "en"
    assert any(p.style.name == "Heading 1" and p.text.strip() == "2 Tests" for p in d.paragraphs)
