"""Data access, scoping and failure isolation. Database tests on the bed."""
import inspect
import logging
from pathlib import Path

import pytest

from conftest import IDS, _sources, block, need, render, status_of

pytestmark = pytest.mark.db
DATA_MODULES = ["platform", "qualification", "control_objectives", "engine", "controls", "superset_db"]


@pytest.mark.parametrize("name", DATA_MODULES)
def test_every_data_function_takes_project_and_system_first(name):
    mod = need("report_renderer.data", name) if False else __import__("importlib").import_module
    try:
        module = mod(f"report_renderer.data.{name}")
    except ModuleNotFoundError:
        pytest.fail(f"missing feature: module report_renderer.data.{name}", pytrace=False)
    public = [f for n, f in inspect.getmembers(module, inspect.isfunction)
              if not n.startswith("_") and f.__module__ == module.__name__]
    assert public, f"report_renderer.data.{name} reads nothing"
    for f in public:
        params = list(inspect.signature(f).parameters)
        assert params[:2] == ["project_id", "system_id"], f"{name}.{f.__name__}{params}"


def test_a_system_of_another_project_raises_not_in_project(sources):
    NotInProject = need("report_renderer.data.scope", "NotInProject")
    pinned_system = need("report_renderer.data.platform", "pinned_system")
    with pytest.raises(NotInProject):
        pinned_system(IDS["A"], IDS["B_V1"], sources=sources)
    assert pinned_system(IDS["A"], IDS["A_V2"], sources=sources)["number"] == 2


def test_the_project_database_name_is_validated():
    name = need("report_renderer.data.scope", "database_name")
    assert name(IDS["A"]) == "project_a0000000000040008000000000000001"
    with pytest.raises(ValueError):
        name("alpha; DROP DATABASE x")


def test_sources_from_the_environment(bed):
    Sources = need("report_renderer.data", "Sources")
    s = Sources.from_env(bed.env())
    assert "report_ro@" in s.platform_dsn and "report_ro@" in s.superset_dsn
    assert "{database}" in s.project_db_template


def test_the_renderers_role_cannot_write(bed):
    r = bed.psql("platform", "INSERT INTO core.project (name, slug) VALUES ('x', 'x-ro-test')", role="report_ro",
                 check=False)
    assert r.returncode != 0
    assert "read-only" in r.stderr or "permission denied" in r.stderr, r.stderr


# a risk is rated by rating_impact and rating_likelihood
def test_mappings_expose_impact_likelihood_rating_and_band(sources):
    mappings = need("report_renderer.data.control_objectives", "mappings")
    rows = {r["risk_id"]: r for r in mappings(IDS["M"], IDS["M_V2"], sources=sources)}
    got = {rid: (r["impact"], r["likelihood"], r["rating"], r["band"]) for rid, r in rows.items()}
    assert got == {"R-1": (5, 4, 20, "Critical"), "R-2": (3, None, None, None), "R-3": (1, 2, 2, "Low"),
                   "R-4": (None, None, None, None), "R-5": (4, None, None, None)}
    assert all("severity" not in r for r in rows.values())


def test_the_renderer_never_names_the_catalogue():
    root = Path(need("report_renderer", "__file__")).parent
    hits = [p for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".j2", ".sql", ".html"}
            and "catalogue" in p.read_text(errors="ignore").lower()]
    assert not hits, hits
    assert len(list(root.rglob("*.py"))) > 1, "missing feature: report_renderer has no code yet"


def test_an_unreachable_source_fails_only_its_blocks(bed, make_deps):
    env = bed.env()
    env["REPORT_SUPERSET_DATABASE_URL"] = env["REPORT_SUPERSET_DATABASE_URL"].replace(f":{bed.port}/", ":1/")
    deps = make_deps(sources=_sources(env))
    chart, text_block, card = block("dashboard_chart", chart_id=IDS["CHART_A"]), block("free_text", text="x"), block("ai_card")
    result = render(deps, [chart, text_block, card])
    assert status_of(result, chart["instance_id"])["status"] == "error"
    assert status_of(result, text_block["instance_id"])["status"] == "ok"
    assert status_of(result, card["instance_id"])["status"] == "ok"


def test_an_unreachable_platform_fails_the_render(bed, make_deps):
    env = bed.env()
    env["REPORT_PLATFORM_DATABASE_URL"] = env["REPORT_PLATFORM_DATABASE_URL"].replace(f":{bed.port}/", ":1/")
    Unavailable = need("report_renderer.errors", "PlatformUnavailable")
    with pytest.raises(Unavailable):
        render(make_deps(sources=_sources(env)), [block("free_text", text="x")])


def test_logs_carry_ids_and_counts_never_bodies(deps, caplog):
    caplog.set_level(logging.DEBUG)
    render(deps, [block("control_answers"), block("dashboard_chart", chart_id=IDS["CHART_A"]),
                  block("free_text", text="PRIVATE-FREE-TEXT"), block("ai_card")])
    for body in ("Documented in the manual", "First look", "PRIVATE-FREE-TEXT", "Scores loan files"):
        assert body not in caplog.text, body


# another project's ids read nothing of it
def test_another_projects_ids_show_nothing_of_it(deps):
    blocks = [block("test_results"),
              block("control_answers", checklists=["cl-b"]),
              block("dashboard_chart", chart_id=IDS["CHART_B"])]
    html = render(deps, blocks)["html"]
    assert "BETAMARK" not in html


def test_the_project_database_lookup_is_remembered_for_a_moment(monkeypatch):
    """Every project read asked the platform database whether the project's database exists, one more
    connection per read; a report opened hundreds. The answer is kept for
    PROJECT_DSN_TTL_S seconds."""
    from report_renderer.data import db

    asked = []
    monkeypatch.setattr(db, "one", lambda dsn, source, sql, params=None: asked.append(params) or {"x": 1})
    monkeypatch.setattr(db, "_DSN_CACHE", {})
    clock = {"t": 100.0}
    monkeypatch.setattr(db, "_now", lambda: clock["t"])

    class S:
        platform_dsn = "postgresql://p/platform"

        def project_dsn(self, name):
            return f"postgresql://p/{name}"

    pid = "a1b2c3d4-0000-4000-8000-000000000002"
    assert db.project_dsn(S(), pid) == db.project_dsn(S(), pid) is not None
    assert len(asked) == 1
    clock["t"] += db.PROJECT_DSN_TTL_S + 1
    db.project_dsn(S(), pid)
    assert len(asked) == 2


def test_controls_reads_share_the_remembered_project_database_lookup(monkeypatch):
    """Controls asked the platform database (uncached) whether the project's
    database exists before every read; load_answers makes four. They now go through db.project_dsn."""
    from report_renderer.data import controls, db

    platform_reads, project_reads = [], []
    monkeypatch.setattr(db, "one", lambda dsn, source, sql, params=None: platform_reads.append(dsn) or {"x": 1})
    monkeypatch.setattr(db, "rows", lambda dsn, source, sql, params=None: project_reads.append(dsn) or [])
    monkeypatch.setattr(db, "_DSN_CACHE", {})

    class S:
        platform_dsn = "postgresql://p/platform"

        def project_dsn(self, name):
            return f"postgresql://p/{name}"

    pid, sid = "a1b2c3d4-0000-4000-8000-000000000002", "a2000000-0000-4000-8000-000000000002"
    assert controls.checklists(pid, sid, sources=S()) == []
    controls.submissions_with_answers(pid, sid, sources=S(), include_archived=False)
    controls.questions(pid, sid, sources=S(), checklist_ids=["c"])
    controls.answers(pid, sid, sources=S(), submission_ids=["s"])
    assert len(project_reads) == 4 and len(platform_reads) == 1


def test_controls_read_none_without_the_project_database(monkeypatch):
    from report_renderer.data import controls, db

    monkeypatch.setattr(db, "one", lambda dsn, source, sql, params=None: None)
    monkeypatch.setattr(db, "_DSN_CACHE", {})

    class S:
        platform_dsn = "postgresql://p/platform"

        def project_dsn(self, name):
            return f"postgresql://p/{name}"

    pid, sid = "a1b2c3d4-0000-4000-8000-000000000003", "a2000000-0000-4000-8000-000000000002"
    assert controls.checklists(pid, sid, sources=S()) is None
    assert controls.submissions_with_answers(pid, sid, sources=S(), include_archived=False) is None
    assert controls.questions(pid, sid, sources=S(), checklist_ids=["c"]) == []
