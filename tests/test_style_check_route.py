"""POST /v1/style/check: the composer asks the renderer whether a template's logo can be used, so the
rule lives once, in report_renderer/style.py logo_problem."""
import pytest

from conftest import need
from test_style import LOGOS

TOKEN = "t0ken-for-tests-" + "x" * 16
H = {"X-Report-Token": TOKEN}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    # The check reads nothing from a database, so the app gets no data sources.
    return TestClient(need("report_service", "create_app")(deps=object(), token=TOKEN, max_body_bytes=4096))


@pytest.mark.parametrize("mime,data_base64,refused", [c[1:] for c in LOGOS], ids=[c[0] for c in LOGOS])
def test_the_check_answers_as_the_render_would(client, mime, data_base64, refused):
    from report_renderer.style import logo_problem

    logo = {"logo": {"mime": mime, "data_base64": data_base64}}
    r = client.post("/v1/style/check", headers=H, json=logo)
    assert r.status_code == 200
    assert r.json() == {"problem": logo_problem(logo)}
    assert (r.json()["problem"] is not None) == refused


def test_a_style_with_no_logo_has_no_problem(client):
    assert client.post("/v1/style/check", headers=H, json={}).json() == {"problem": None}


def test_the_check_needs_the_token(client):
    assert client.post("/v1/style/check", json={}).status_code == 401


def test_a_body_that_is_not_an_object_is_422(client):
    for body in (b"[]", b"not json"):
        r = client.post("/v1/style/check", headers={**H, "Content-Type": "application/json"}, content=body)
        assert r.status_code == 422


def test_a_body_past_the_limit_is_413(client):
    big = {"logo": {"mime": "image/png", "data_base64": "A" * 8192}}
    assert client.post("/v1/style/check", headers=H, json=big).status_code == 413
