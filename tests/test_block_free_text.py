"""Free text block."""
import pytest

from conftest import render_one

pytestmark = pytest.mark.db


def test_paragraphs_and_line_breaks_plain_text_only(deps):
    body = "First para <script>x</script>\nsecond line\n\nSecond **para**"
    _, s, node, result = render_one(deps, "free_text", text=body)
    paragraphs = node.find_all("p")
    assert len(paragraphs) == 2
    assert paragraphs[0].find("br") is not None
    assert node.find("script") is None and "&lt;script&gt;" in str(node)
    assert "**para**" in paragraphs[1].get_text()
    assert node.find("strong") is None


def test_never_empty_or_stale(deps):
    _, s, *_ = render_one(deps, "free_text", text="x")        # Alpha v2 has a newer version
    assert s["status"] == "ok"
    _, s, *_ = render_one(deps, "free_text", project="C", system="C_V1", text="y")
    assert s["status"] == "ok"


# text is required
def test_free_text_without_text_is_an_error(deps):
    _, s, *_ = render_one(deps, "free_text")
    assert s["status"] == "error"
    assert any(n.startswith("Invalid options: text") for n in s["notices"])
