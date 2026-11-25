"""Template-level rendering safety: what the renderer may put into HTML.

These render real Jinja2 output (render_html) so the guards are verified at the
boundary that actually produces the document, not on the resolver alone.
"""
from render import render_html

PNG = "data:image/png;base64,iVBORw0KGgo="


def _snapshot(widgets, evaluations=(), sections=("evaluations", "dashboard")):
    return {
        "project": {"pid": "p", "name": "Project", "description": ""},
        "system": {},
        "sections": list(sections),
        "evaluations": list(evaluations),
        "dashboard": {"widgets": list(widgets)},
    }


def test_malicious_svg_is_never_inserted_into_rendered_html():
    malicious = "<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    snapshot = _snapshot([
        {"key": "c1", "kind": "chart", "title": "Legacy svg", "svg": malicious},
        {"key": "c2", "kind": "chart", "title": "Fresh png", "image": PNG},
    ])
    page = render_html(snapshot).decode("utf-8")
    assert "<svg" not in page
    assert "<script>alert(1)</script>" not in page
    # the fresh PNG still renders
    assert '<img class="plot-item plot-image" src="data:image/png;base64,iVBORw0KGgo="' in page
    # the SVG-only legacy widget gets the unavailable message instead
    assert "Chart unavailable — no image was exported." in page


def test_dashboard_svg_only_widget_shows_unavailable_message():
    snapshot = _snapshot([
        {"key": "c1", "kind": "chart", "title": "Legacy", "svg": "<svg/>"},
    ], sections=("dashboard",))
    page = render_html(snapshot).decode("utf-8")
    assert "Chart unavailable — no image was exported." in page
    assert "<svg" not in page
    assert '<img' not in page


def test_missing_evaluation_panel_is_guarded_while_others_render():
    evaluations = [{
        "task": "eval",
        "status": "Done",
        "plots": [{
            "title": "Accuracy",
            "panels": [
                {"label": "en", "image": PNG},
                {"label": "de", "image": ""},
            ],
        }],
    }]
    page = render_html(_snapshot([], evaluations)).decode("utf-8")
    assert page.count('<img class="plot-item plot-image" src="data:image/png') == 1
    assert "Panel unavailable — no image was exported." in page
    assert '<img class="plot-item plot-image" src=""' not in page


def test_html_output_remains_self_contained():
    snapshot = _snapshot([
        {"key": "c1", "kind": "chart", "title": "New", "image": PNG},
    ], sections=("dashboard",))
    page = render_html(snapshot).decode("utf-8")
    assert page.lstrip().startswith("<!DOCTYPE html>")
    # the document carries its own stylesheet (no external references needed)
    assert "<style>" in page
    assert "data:image/png" in page
