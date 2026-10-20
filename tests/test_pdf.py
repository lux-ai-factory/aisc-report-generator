"""HTML to PDF."""
import base64

import pytest

from conftest import PNG, need


def fetcher():
    return need("report_renderer.pdf", "url_fetcher")


def test_data_uris_are_fetched():
    data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
    result = fetcher()(data_uri)
    body = result.get("string") if isinstance(result, dict) else getattr(result, "string", None)
    assert body == PNG


@pytest.mark.parametrize("url", ["http://example.com/x.png", "https://host.docker.internal:8188/api/v1/chart/1",
                                 "file:///etc/passwd", "ftp://x/y"])
def test_every_other_url_is_refused(url):
    with pytest.raises(Exception):
        fetcher()(url)


def test_html_becomes_a_pdf():
    html_to_pdf = need("report_renderer.pdf", "html_to_pdf")
    pdf = html_to_pdf("<html><body><p>Hello</p></body></html>")
    assert pdf[:5] == b"%PDF-"


def test_an_external_image_is_not_fetched(monkeypatch):
    """A remote <img> in the HTML is refused by the fetcher, not downloaded."""
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("the renderer opened a URL")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    html_to_pdf = need("report_renderer.pdf", "html_to_pdf")
    pdf = html_to_pdf('<html><body><img src="http://example.com/x.png"><img src="file:///etc/hostname"></body></html>')
    assert pdf[:5] == b"%PDF-"
