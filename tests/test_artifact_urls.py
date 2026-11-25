import asyncio
import base64
from time import monotonic
from unittest.mock import patch

import httpx
import pytest

from app import resolve_artifacts

ORIGIN = "http://aisc-backend:8000"
PREFIX = f"{ORIGIN}/api/v1/projects/p/report-artifacts/"
PNG = b"\x89PNG\r\n\x1a\n"
AsyncClient = httpx.AsyncClient


def resolve(snapshot, handler):
    def client(**kwargs):
        return AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    with patch("app.httpx.AsyncClient", side_effect=client):
        asyncio.run(resolve_artifacts(snapshot))


def test_fetches_internal_images_and_embeds_them(monkeypatch):
    monkeypatch.setattr("app.EXPECTED", b"test-token")
    snapshot = {"dashboard": {"widgets": [{"image": PREFIX + "a"}]}}

    def download(request):
        assert request.headers["X-AISC-Service-Token"] == "test-token"
        return httpx.Response(200, content=PNG)

    resolve(snapshot, download)
    assert snapshot["dashboard"]["widgets"][0]["image"] == (
        "data:image/png;base64," + base64.b64encode(PNG).decode()
    )


def test_rejects_external_urls():
    with pytest.raises(ValueError):
        asyncio.run(resolve_artifacts({"image": "http://external.example/report-artifacts/a"}))


def test_downloads_four_at_once_deduplicates_and_preserves_associations():
    active = peak = 0
    calls = []
    four_started = asyncio.Event()
    urls = [PREFIX + str(index) for index in range(8)]
    snapshot = {"items": [{"image": url} for url in urls + [urls[0]]]}

    async def download(request):
        nonlocal active, peak
        calls.append(str(request.url))
        active += 1
        peak = max(peak, active)
        if active == 4:
            four_started.set()
        await asyncio.wait_for(four_started.wait(), timeout=1)
        await asyncio.sleep(0)
        active -= 1
        return httpx.Response(200, content=PNG + str(request.url).encode())

    resolve(snapshot, download)
    assert len(calls) == 8
    assert peak == 4
    for item, url in zip(snapshot["items"], urls + [urls[0]]):
        assert base64.b64decode(item["image"].split(",", 1)[1]) == PNG + url.encode()


@pytest.mark.parametrize("failure", ["network", "http", "invalid", "oversize", "redirect"])
def test_download_failure_marks_that_url_unavailable_and_keeps_others(failure):
    url, other = PREFIX + "a", PREFIX + "b"
    snapshot = {"items": [{"image": url}, {"image": url}, {"image": other}]}
    fetched = []

    def download(request):
        fetched.append(str(request.url))
        if str(request.url) == other:
            return httpx.Response(200, content=PNG)
        if failure == "network":
            raise httpx.ConnectError("unavailable", request=request)
        if failure == "http":
            return httpx.Response(404)
        if failure == "invalid":
            return httpx.Response(200, content=b"invalid")
        if failure == "oversize":
            return httpx.Response(200, content=PNG + b"x" * 2_000_000)
        return httpx.Response(302, headers={"Location": "https://external.example/leak"})

    resolve(snapshot, download)
    assert [item["image"] for item in snapshot["items"][:2]] == ["", ""]
    assert snapshot["items"][2]["image"].startswith("data:image/png;base64,")
    assert fetched == [url, other]  # redirects never receive the service token


def test_non_png_images_are_never_embedded():
    png = "data:image/png;base64,iVBORw0KGgo="
    malicious = "<svg><script>alert(1)</script></svg>"
    snapshot = {"items": [
        {"image": "data:image/svg+xml;base64," + base64.b64encode(malicious.encode()).decode()},
        {"image": png}, {"image": malicious},
    ]}
    asyncio.run(resolve_artifacts(snapshot))
    assert [item["image"] for item in snapshot["items"]] == ["", png, ""]


def test_exhausted_download_budget_marks_charts_unavailable_without_fetching(monkeypatch):
    monkeypatch.setattr("app.ARTIFACT_BUDGET_SECONDS", 0)
    snapshot = {"items": [{"image": PREFIX + "a"}, {"image": PREFIX + "a"}]}
    with patch("app.httpx.AsyncClient") as client:
        asyncio.run(resolve_artifacts(snapshot))
        client.assert_not_called()
    assert all(item["image"] == "" for item in snapshot["items"])


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_slow_download_is_cut_off_at_the_deadline(monkeypatch, phase):
    """Cancel in-progress headers or a dripping body, close streams, skip queued
    URLs, retain completed charts and continue rendering within the total budget."""
    monkeypatch.setattr("app.ARTIFACT_BUDGET_SECONDS", 0.08)
    healthy = PREFIX + "healthy"
    slow = [PREFIX + f"slow-{index}" for index in range(6)]
    snapshot = {"items": [{"image": url} for url in [healthy, *slow, slow[0]]]}
    started = []
    cancelled = []
    closed = []

    class Drip(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield PNG
            while True:
                await asyncio.sleep(0.005)
                yield b"x"

        async def aclose(self):
            closed.append(True)

    async def download(request):
        if str(request.url) == healthy:
            return httpx.Response(200, content=PNG)
        started.append(str(request.url))
        if phase == "headers":
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(str(request.url))
        return httpx.Response(200, stream=Drip())

    before = monotonic()
    resolve(snapshot, download)
    assert monotonic() - before < 0.6
    assert len(started) == 4  # two queued URLs never start after cancellation
    assert len(cancelled if phase == "headers" else closed) == 4
    assert snapshot["items"][0]["image"].startswith("data:image/png;base64,")
    assert all(item["image"] == "" for item in snapshot["items"][1:])

    from render import render_html

    snapshot["sections"] = ["dashboard"]
    snapshot["dashboard"] = {"widgets": [
        {"key": str(index), "kind": "chart", "title": "Chart", **item}
        for index, item in enumerate(snapshot.pop("items"))
    ]}
    html = render_html(snapshot).decode()
    assert html.count('<img class="plot-item plot-image"') == 1
    assert "Chart unavailable" in html
