"""POST /v1/render is bounded: a body over the size cap is 413 before it is parsed, and once the render
slots are all taken a further render is 503 at once, instead of queueing until the service runs out of
memory or threads. Both bounds come from the environment, with safe defaults.

No database: the render itself is replaced by a fake, so only the route's own bounds are under test."""
import json
import threading

import pytest
from fastapi.testclient import TestClient

import report_service

TOKEN = "t0ken-for-limit-tests-" + "x" * 16
H = {"X-Report-Token": TOKEN, "Content-Type": "application/json"}
SNAP = {"project_id": "p", "blocks": []}


@pytest.fixture
def fake_render(monkeypatch):
    calls = []

    def render(snapshot, deps):
        calls.append(snapshot)
        return {"html": "<p>ok</p>", "fingerprint": "f", "block_statuses": []}

    monkeypatch.setattr(report_service, "render", render)
    return calls


def app(**kw):
    return report_service.create_app(deps=object(), token=TOKEN, **kw)


def test_a_render_within_the_bounds_still_answers(fake_render):
    r = TestClient(app()).post("/v1/render", headers=H, content=json.dumps(SNAP))
    assert r.status_code == 200 and r.json()["html"] == "<p>ok</p>"
    assert fake_render == [SNAP]


def test_a_body_over_the_cap_is_413_and_never_rendered(fake_render):
    body = json.dumps({**SNAP, "pad": "x" * 2000})
    r = TestClient(app(max_body_bytes=1000)).post("/v1/render", headers=H, content=body)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "too_large"
    assert fake_render == []


def test_a_chunked_body_over_the_cap_is_413(fake_render):
    """No Content-Length to trust: the cap holds on the bytes actually read."""
    def chunks():
        yield b'{"project_id": "p", "pad": "'
        for _ in range(20):
            yield b"x" * 100
        yield b'"}'

    r = TestClient(app(max_body_bytes=1000)).post("/v1/render", headers=H, content=chunks())
    assert r.status_code == 413
    assert fake_render == []


def test_a_body_that_is_not_a_json_object_is_422(fake_render):
    client = TestClient(app())
    assert client.post("/v1/render", headers=H, content=b"not json").status_code == 422
    assert client.post("/v1/render", headers=H, content=b"[1, 2]").status_code == 422
    assert fake_render == []


def test_when_every_render_slot_is_taken_a_further_render_is_503(monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow(snapshot, deps):
        started.set()
        release.wait(10)
        return {"html": "", "fingerprint": "f", "block_statuses": []}

    monkeypatch.setattr(report_service, "render", slow)
    with TestClient(app(max_concurrent_renders=1)) as client:
        first = {}
        t = threading.Thread(target=lambda: first.setdefault(
            "r", client.post("/v1/render", headers=H, content=json.dumps(SNAP))))
        t.start()
        assert started.wait(10)
        busy = client.post("/v1/render", headers=H, content=json.dumps(SNAP))
        release.set()
        t.join(10)
    assert busy.status_code == 503 and busy.json()["error"]["code"] == "busy"
    assert first["r"].status_code == 200


def test_a_slot_is_given_back_when_the_render_fails(monkeypatch):
    def boom(snapshot, deps):
        raise report_service.PlatformUnavailable("down")

    monkeypatch.setattr(report_service, "render", boom)
    client = TestClient(app(max_concurrent_renders=1))
    assert client.post("/v1/render", headers=H, content=json.dumps(SNAP)).status_code == 503
    monkeypatch.setattr(report_service, "render", lambda s, d: {"html": "", "fingerprint": "f",
                                                                "block_statuses": []})
    assert client.post("/v1/render", headers=H, content=json.dumps(SNAP)).status_code == 200


def test_the_bounds_come_from_the_environment(fake_render, monkeypatch):
    monkeypatch.setenv("REPORT_RENDER_MAX_BYTES", "1000")
    monkeypatch.setenv("REPORT_RENDER_CONCURRENCY", "3")
    r = TestClient(app()).post("/v1/render", headers=H, content=json.dumps({**SNAP, "pad": "x" * 2000}))
    assert r.status_code == 413
    assert report_service.render_limits({"REPORT_RENDER_MAX_BYTES": "1000",
                                         "REPORT_RENDER_CONCURRENCY": "3"}) == (1000, 3)


def test_the_defaults_are_bounded():
    max_bytes, slots = report_service.render_limits({})
    assert 0 < max_bytes <= 32 * 1024 * 1024
    assert 0 < slots <= 16


@pytest.mark.parametrize("name,value", [("REPORT_RENDER_MAX_BYTES", "0"), ("REPORT_RENDER_MAX_BYTES", "lots"),
                                        ("REPORT_RENDER_CONCURRENCY", "-1"), ("REPORT_RENDER_CONCURRENCY", "x")])
def test_a_bad_bound_in_the_environment_stops_the_start(name, value):
    with pytest.raises(RuntimeError, match=name):
        report_service.render_limits({name: value})
