"""The renderer's HTTP interface, called only by the composer: `report_service.create_app(deps=..., token=...)`."""
import base64
import hmac
import logging
import tempfile

import pytest

from conftest import IDS, block, lazily, need, snapshot

pytestmark = pytest.mark.db
TOKEN = "t0ken-for-tests-" + "x" * 16
H = {"X-Report-Token": TOKEN}


@pytest.fixture
def client(deps):
    from fastapi.testclient import TestClient

    return lazily(lambda: TestClient(need("report_service", "create_app")(deps=deps, token=TOKEN)))


@pytest.mark.parametrize("method,path", [("get", "/v1/block-types"), ("post", "/v1/choices"), ("post", "/v1/render")])
def test_no_token_no_answer(client, method, path):
    kw = {"json": {}} if method == "post" else {}      # TestClient.get takes no json=
    assert getattr(client, method)(path, **kw).status_code == 401
    assert getattr(client, method)(path, headers={"X-Report-Token": "wrong"}, **kw).status_code == 401


def test_the_token_is_compared_in_constant_time(client, monkeypatch):
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    client.get("/v1/block-types", headers=H)
    assert calls


def test_the_token_comes_from_the_environment(deps, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("REPORT_SERVICE_TOKEN", "from-env-token-000000000000")
    app = need("report_service", "create_app")(deps=deps)
    c = TestClient(app)
    assert c.get("/v1/block-types", headers={"X-Report-Token": "from-env-token-000000000000"}).status_code == 200


def test_health(client):
    r = client.get("/health", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "free_text" in body["block_types"] and "cover" in body["block_types"]
    assert "tool_renderers" in body


def test_block_types(client):
    r = client.get("/v1/block-types", headers=H)
    assert r.status_code == 200
    types = {t["type_id"]: t for t in r.json()}
    assert len(types) >= 9
    for t in types.values():
        assert set(t) >= {"type_id", "title", "contract_version", "options_schema", "default_options"}
    assert types["free_text"]["options_schema"]["properties"]["title"]["maxLength"] == 200


def test_choices(client):
    r = client.post("/v1/choices", headers=H,
                    json={"project_id": IDS["A"], "system_id": IDS["A_V2"], "block_type": "dashboard_chart"})
    assert r.status_code == 200
    assert {c["value"] for c in r.json()["chart_id"]} == {IDS["CHART_A"], IDS["CHART_A2"]}


def test_render_preview(client):
    b = block("free_text", text="hello service")
    r = client.post("/v1/render", headers=H, json=snapshot([b]))
    assert r.status_code == 200
    body = r.json()
    assert "hello service" in body["html"]
    assert body["block_statuses"][0]["instance_id"] == b["instance_id"]


def test_render_pdf(client):
    r = client.post("/v1/render", headers=H, json=snapshot([block("free_text", text="x")], mode="pdf"))
    assert r.status_code == 200
    body = r.json()
    assert base64.b64decode(body["pdf_base64"])[:5] == b"%PDF-" and len(body["sha256"]) == 64


def test_a_bad_snapshot_is_422_with_problems(client):
    s = snapshot([block("free_text", text="x")])
    s.pop("system_id")
    r = client.post("/v1/render", headers=H, json=s)
    assert r.status_code == 422
    problems = r.json()["problems"]
    assert problems and set(problems[0]) == {"instance_id", "code", "pointer", "message"}


def test_system_not_in_project_is_404(client):
    r = client.post("/v1/render", headers=H, json=snapshot([block("free_text", text="x")], system="B_V1"))
    assert r.status_code == 404


def test_a_project_that_does_not_exist_is_404_not_an_empty_report(client):
    """A random project id rendered a 200 report with an empty name and version 0: no
    project database meant a stand-in version, and no core.project row went unnoticed."""
    import uuid

    snap = snapshot([block("free_text", text="x")])
    snap["project_id"], snap["system_id"] = str(uuid.uuid4()), str(uuid.uuid4())
    assert client.post("/v1/render", headers=H, json=snap).status_code == 404


@pytest.mark.parametrize("path", ["/generate?project_id=1", "/reports/assessment_report.pdf"])
def test_the_legacy_routes_are_gone(client, path):
    assert client.get(path, headers=H).status_code == 404


def test_no_files_left_behind(client, tmp_path, monkeypatch):
    work, tmp = tmp_path / "cwd", tmp_path / "tmp"
    work.mkdir(), tmp.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    r = client.post("/v1/render", headers=H, json=snapshot([block("cover"), block("free_text", text="x")], mode="pdf"))
    assert r.status_code == 200
    assert list(work.iterdir()) == [] and list(tmp.iterdir()) == []


def test_platform_unreachable_is_503(bed, make_deps):
    from fastapi.testclient import TestClient

    from conftest import _sources

    env = bed.env()
    env["REPORT_PLATFORM_DATABASE_URL"] = env["REPORT_PLATFORM_DATABASE_URL"].replace(f":{bed.port}/", ":1/")
    app = need("report_service", "create_app")(deps=make_deps(sources=_sources(env)), token=TOKEN)
    r = TestClient(app).post("/v1/render", headers=H, json=snapshot([block("free_text", text="x")]))
    assert r.status_code == 503


def test_the_token_is_never_echoed(client, caplog):
    caplog.set_level(logging.DEBUG)
    responses = [client.get("/health", headers=H), client.get("/v1/block-types", headers=H),
                 client.post("/v1/render", headers=H, json=snapshot([block("cover")])),
                 client.post("/v1/render", headers={"X-Report-Token": "wrong"}, json={})]
    for r in responses:
        assert TOKEN not in r.text and TOKEN not in str(r.headers)
    assert TOKEN not in caplog.text
    assert "report_ro:report_ro" not in caplog.text   # nor a database password


# templates: the composer offers the fonts the renderer can put in a PDF
def test_the_fonts_route_lists_them(client):
    r = client.get("/v1/fonts", headers=H)
    assert r.status_code == 200
    ids = [f["id"] for f in r.json()]
    assert "inter" in ids and all(set(f) >= {"id", "label"} for f in r.json())
