"""Cover block. Database tests on the bed."""
import pytest

from conftest import block, render, render_one, section, text

pytestmark = pytest.mark.db


def test_the_cover_names_everything(deps):
    t, s, _, _ = render_one(deps, "cover")
    for expected in ("AI system assessment report", "Alpha project", "Alpha scorer", "Version 2", "(1.0)",
                     "Acme AI", "2026-09-20", "Quarterly report", "revision 4"):
        assert expected in t, expected
    assert s["status"] in ("ok", "stale")


def test_title_and_subtitle(deps):
    t, *_ = render_one(deps, "cover", report_title="Credit model review", subtitle="Second round")
    assert "Credit model review" in t and "Second round" in t
    assert "AI system assessment report" not in t


def test_release_and_provider_only_when_set(deps):
    t, *_ = render_one(deps, "cover", project="C", system="C_V1")
    assert "Gamma model" in t and "Version 1" in t
    assert "()" not in t and "None" not in t


def _pdf_text(result):
    import base64
    import io

    from pypdf import PdfReader

    return " ".join(p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(result["pdf_base64"]))).pages)


def test_generated_by_in_pdf_mode_is_the_requester(deps):
    result = render(deps, [block("cover")], mode="pdf", requested_by="Alice Editor")
    assert "Alice Editor" in _pdf_text(result)


def test_generated_by_in_preview_says_preview(deps):
    b = block("cover")
    html = render(deps, [b], mode="preview", requested_by="Alice Editor")["html"]
    t = text(section(html, b["instance_id"]))
    assert "preview" in t.lower() and "Alice Editor" not in t


def test_generated_by_can_be_hidden(deps):
    t, *_ = render_one(deps, "cover", show_generated_by=False)
    assert "preview" not in t.lower()


def test_the_cover_says_when_a_newer_version_exists(deps):
    t, *_ = render_one(deps, "cover")
    assert "This report covers version 2. Version 3 is newer." in t
    t, *_ = render_one(deps, "cover", system="A_V1")
    assert "This report covers version 1. Version 3 is newer." in t


def test_no_banner_on_the_latest(deps):
    t, *_ = render_one(deps, "cover", system="A_V3")
    assert "is newer" not in t


def test_the_cover_is_never_empty(deps):
    _, s, _, _ = render_one(deps, "cover", project="C", system="C_V1")
    assert s["status"] == "ok"


def test_the_marking_labels_are_kept_in_one_place():
    """The cover block kept its own copy of document.MARKING_LABELS."""
    from report_renderer import document
    from report_renderer.blocks import cover

    assert cover.MARKING_LABELS is document.MARKING_LABELS
