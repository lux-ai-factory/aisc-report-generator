"""Exported results drawn from saved plots handed in directly. No database."""
from datetime import datetime
from types import SimpleNamespace

from bs4 import BeautifulSoup

from report_renderer.blocks.superset_exports import SupersetExportsBlock

SVG = b'<svg width="10" height="10" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'


def plot(dashboard_id, title, chart):
    return {"dashboard_id": dashboard_id, "dashboard_title": title, "chart": chart, "tags": [], "comment": "",
            "author_name": "Alice", "created_at": datetime(2026, 2, 1), "svg": SVG}


def render(rows):
    ctx = SimpleNamespace(t=lambda text, **kw: text.format(**kw))
    result = SupersetExportsBlock().render({"exports": rows}, {"dashboards": "all"}, ctx)
    return BeautifulSoup(result.html, "html.parser")


def test_two_blocks_with_the_same_title_stay_two_subsections():
    node = render([plot(1, "Results", "By register"), plot(2, "Results", "By category")])
    blocks = node.select(".export-block")
    assert [b.find("h3").get_text(strip=True) for b in blocks] == ["Results", "Results"]
    assert [[h.get_text(strip=True) for h in b.find_all("h4")] for b in blocks] == [["By register"], ["By category"]]

