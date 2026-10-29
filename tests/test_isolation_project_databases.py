"""The renderer on one database per project.

The platform database holds only core.project (and core.project_member); the card versions are
`project.system` and every module's tables (qualification, control_objectives, engine, controls) live
in the project's own database `project_<hex>`, read as `report_ro` through REPORT_PROJECT_DB_URL. These
tests run on a second throwaway bed in exactly that shape (the superproject's
scripts/lib/report_bed_isolated.py: the report bed's seed, moved per project, with the shared schemas
and core.system dropped from `platform`), so a renderer that read core.system or the module schemas
from `platform` would fail them.

Every name of the renderer is looked up with `need`, so a missing feature fails its test, never the
collection. Needs AISC_INSTALL_DIR at a superproject checkout with scripts/lib/report_bed_isolated.py
(the default is set in conftest.py).
"""
from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

import pytest

from conftest import (AISC_INSTALL, FIXED_NOW, IDS, RecordingImages, block, controls_keep_closed_answers, lazily,
                      need, snapshot)

pytestmark = pytest.mark.db

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "report_renderer" / "data"
TOKEN = "t0ken-for-isolation-" + "x" * 12
H = {"X-Report-Token": TOKEN}

#: a project made only in this file: its database has project.system but lacks module schemas/tables
X = "9a000000-0000-4000-8000-000000000001"
X_V1 = "9a100000-0000-4000-8000-000000000001"

#: block types whose data comes from a project's database (cover, free_text, chapter: no module data)
DATA_BLOCKS = ["ai_card", "risk_classification", "control_objectives", "test_results", "control_answers",
               "summary_coverage", "key_figures"]
MOVED_MODULES = ["qualification", "control_objectives", "engine"]


def _hex(pid: str) -> str:
    return pid.replace("-", "")


def _db(pid: str) -> str:
    return "project_" + _hex(pid)


# The isolated bed.


@pytest.fixture(scope="session")
def iso_bed():
    try:
        import sys

        sys.path.insert(0, str(AISC_INSTALL / "scripts/lib"))
        iso = importlib.import_module("report_bed_isolated")
    except ModuleNotFoundError:
        pytest.fail("AISC_INSTALL_DIR must point at the superproject (scripts/lib/report_bed_isolated.py)",
                    pytrace=False)
    iso.report_bed.check_dsn_env()
    b = iso.build_isolated("iso-R-renderer", modules=True)
    try:
        _add_project_without_module_tables(iso, b)
        controls_keep_closed_answers(b)
        yield b
    finally:
        b.stop()


def _add_project_without_module_tables(iso, b):
    """Project X: a core.project row and a database with project.system (one version) and controls, an
    EMPTY qualification schema (no tables) and no control_objectives or engine schema."""
    b.psql("platform", f"INSERT INTO core.project (pid, name, slug) VALUES ('{X}', 'Xray project', 'xray')")
    b.psql("platform", f"INSERT INTO core.project_member (project_id, subject, email, role)"
                       f" VALUES ('{X}', 'alice', 'alice@localhost', 'editor')")
    iso.report_bed._project_database(b.t, X)
    b.psql(_db(X), f"""
        CREATE SCHEMA IF NOT EXISTS project;
        CREATE TABLE IF NOT EXISTS project.system (pid uuid PRIMARY KEY, number integer NOT NULL UNIQUE,
          name text NOT NULL, version text, provider text, description text,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
          created_by text);
        INSERT INTO project.system (pid, number, name) VALUES ('{X_V1}', 1, 'Xray model');
        GRANT CONNECT ON DATABASE "{_db(X)}" TO report_ro;
        GRANT USAGE ON SCHEMA project TO report_ro;
        GRANT SELECT ON project.system TO report_ro;
        DROP SCHEMA IF EXISTS qualification CASCADE;
        CREATE SCHEMA qualification;
        GRANT USAGE ON SCHEMA qualification TO report_ro;
        DROP SCHEMA IF EXISTS control_objectives CASCADE;
        DROP SCHEMA IF EXISTS engine CASCADE;
    """)


@pytest.fixture(scope="session")
def iso_sources(iso_bed):
    def make():
        Sources = need("report_renderer.data", "Sources")
        env = iso_bed.env()
        return Sources(platform_dsn=env["REPORT_PLATFORM_DATABASE_URL"],
                       superset_dsn=env["REPORT_SUPERSET_DATABASE_URL"],
                       project_db_template=env["REPORT_PROJECT_DB_URL"],
                       airo_vocab_path=env["REPORT_AIRO_VOCAB_PATH"],
                       objectives_csv_path=env["REPORT_OBJECTIVES_CSV_PATH"],
                       superset_url="http://superset.invalid:8188")

    return lazily(make)


@pytest.fixture
def iso_deps(iso_sources, registry):
    def make(**over):
        kw = dict(registry=registry, sources=iso_sources, images=RecordingImages(), clock=lambda: FIXED_NOW,
                  chart_data=None)
        kw.update(over)
        return need("report_renderer.context", "Deps")(**kw)

    return lazily(make)


def iso_render(deps, blocks, **kw) -> dict:
    return need("report_renderer.document", "render")(snapshot(blocks, **kw), deps)


def _render_with(deps, blocks, project, system) -> dict:
    snap = snapshot(blocks)
    snap["project_id"], snap["system_id"] = project, system
    return need("report_renderer.document", "render")(snap, deps)


def test_the_isolated_bed_has_the_isolated_shape(iso_bed):
    """The fixture itself (not a renderer requirement): platform has no module schema and no core.system;
    Alpha's database has its three versions and its own module rows only."""
    schemas = iso_bed.scalar("platform", "SELECT string_agg(nspname, ',' ORDER BY nspname) FROM pg_namespace"
                                         " WHERE nspname IN ('qualification', 'control_objectives', 'engine',"
                                         " 'report_composer')")
    assert schemas in ("", None)
    assert iso_bed.scalar("platform", "SELECT to_regclass('core.system') IS NULL") == "t"
    assert iso_bed.scalar(_db(IDS["A"]), "SELECT count(*) FROM project.system") == "3"
    assert iso_bed.scalar(_db(IDS["B"]), "SELECT count(*) FROM project.system") == "1"
    assert iso_bed.scalar(_db(IDS["A"]), f"SELECT count(*) FROM engine.aisc_backend_evaluation e JOIN engine.aisc_backend_project p"
                                         f" ON p.id = e.project_id WHERE p.project_id <> '{IDS['A']}'") == "0"


# The data modules read the project's database.


def test_no_module_of_the_renderer_names_core_system():
    """No module reads core.system: the versions are project.system."""
    hits = [str(p.relative_to(ROOT)) for p in (ROOT / "report_renderer").rglob("*.py")
            if "core.system" in p.read_text(encoding="utf-8")]
    assert not hits, f"still reading the shared card versions: {hits}"


#: short engine table names that do not exist; the engine's real tables are aisc_backend_<model>
ENGINE_SHORT_NAMES = ["evaluation", "evaluation_plugin", "evaluation_input", "plugin", "plugin_config",
                      "project", "observation", "measurement", "metric", "metric_category", "artifact",
                      "ai_component", "ai_system", "derived", "direct", "project_config",
                      # the two many-to-many tables
                      "metric_category_metrics", "plugin_config_project_config"]


def _short_name_reads(text: str) -> list[str]:
    """engine.<short>, quoted or not ("engine"."evaluation", engine."plugin"), never engine.aisc_backend_*."""
    names = "|".join(sorted(ENGINE_SHORT_NAMES, key=len, reverse=True))
    short = re.compile(r'(?<![\w."])"?engine"?\s*\.\s*"?(' + names + r')"?(?![\w])')
    return [m.group(0) for m in short.finditer(text)]


def test_the_short_name_guard_catches_every_form():
    """The two many-to-many tables and the quoted forms are caught too; the engine's real
    aisc_backend_* names are not."""
    for sql in ("FROM engine.metric_category_metrics", "JOIN engine.plugin_config_project_config pc",
                'FROM "engine"."evaluation" e', 'FROM engine."measurement"', 'JOIN "engine".plugin p'):
        assert _short_name_reads(sql), sql
    for sql in ("FROM engine.aisc_backend_evaluation e", 'FROM "engine"."aisc_backend_metriccategory_metrics"',
                "engine.evaluation_pid_idx_x", "myengine.evaluation"):
        assert not _short_name_reads(sql), sql


def test_no_module_of_the_renderer_names_an_engine_table_by_its_short_name():
    """The engine's tables are named aisc_backend_<model>, so a read of engine.<short name> hits a
    missing table, which reads as empty and hides the data silently."""
    hits = [f"{p.relative_to(ROOT)}: {hit}" for p in (ROOT / "report_renderer").rglob("*.py")
            for hit in _short_name_reads(p.read_text(encoding="utf-8"))]
    assert not hits, f"engine tables by the short name: {hits}"


@pytest.mark.parametrize("module", MOVED_MODULES)
def test_the_module_readers_never_use_the_platform_dsn(module):
    """Qualification, control_objectives and engine connect to the project database, not `platform`."""
    source = (DATA / f"{module}.py").read_text(encoding="utf-8")
    assert "platform_dsn" not in source, f"report_renderer/data/{module}.py still reads the platform database"


def test_platform_py_reads_only_core_project_and_pg_database():
    """data/platform.py reads core.project (and pg_database) from REPORT_PLATFORM_DATABASE_URL; the
    version readers (pinned_system, newer_versions, older_versions) read project.system of the project."""
    source = (DATA / "platform.py").read_text(encoding="utf-8")
    tables = set(re.findall(r"\b(?:FROM|JOIN)\s+([a-z_]+\.[a-z_]+|pg_database)\b", source, re.I))
    assert tables <= {"core.project", "pg_database", "project.system"}, tables
    assert "project.system" in tables, "the version readers must read project.system"


class _Spy:
    """A psycopg connection that records (database, sql) of every execute."""

    def __init__(self, conn, log):
        self._conn, self._log = conn, log
        self._db = conn.info.dbname

    def execute(self, sql, *a, **k):
        self._log.append((self._db, str(sql)))
        return self._conn.execute(sql, *a, **k)

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def spied(monkeypatch):
    import psycopg

    log: list[tuple[str, str]] = []
    real = psycopg.connect

    def spy(*a, **k):
        return _Spy(real(*a, **k), log)

    monkeypatch.setattr(psycopg, "connect", spy)
    return log


def test_a_full_report_reads_platform_only_for_core_project(iso_deps, spied):
    """Rendering Alpha v2 with every data block: on `platform` only core.project and
    pg_database are named; the module data comes from Alpha's own database; Beta's is never opened."""
    blocks = [block(t) for t in DATA_BLOCKS] + [block("cover")]
    result = iso_render(iso_deps, blocks)
    errors = [s for s in result["block_statuses"] if s["status"] == "error"]
    assert not errors, errors
    by_db: dict[str, set[str]] = {}
    for db, sql in spied:
        by_db.setdefault(db, set()).update(
            t.lower() for t in re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_]+\.[A-Za-z_]+|pg_database)\b", sql, re.I))
    assert by_db.get("platform", set()) <= {"core.project", "pg_database"}, by_db.get("platform")
    alpha = by_db.get(_db(IDS["A"]), set())
    for schema in ("project.", "qualification.", "control_objectives.", "engine.", "controls."):
        assert any(t.startswith(schema) for t in alpha), f"nothing read from {schema}* in Alpha's database"
    assert _db(IDS["B"]) not in by_db, "Beta's database was opened for a report of Alpha"


def test_versions_come_from_the_projects_database(iso_sources):
    """pinned_system, newer_versions, older_versions read project.system of Alpha's database."""
    platform = importlib.import_module("report_renderer.data.platform")
    assert platform.pinned_system(IDS["A"], IDS["A_V2"], sources=iso_sources)["number"] == 2
    assert [v["number"] for v in platform.newer_versions(IDS["A"], IDS["A_V2"], sources=iso_sources)] == [3]
    assert [v["number"] for v in platform.older_versions(IDS["A"], IDS["A_V2"], sources=iso_sources)] == [1]


def test_module_data_of_the_pinned_version_from_the_projects_database(iso_sources):
    """Card, assessment and evaluations of Alpha v2 are read from Alpha's database, scoped by system_id."""
    q = importlib.import_module("report_renderer.data.qualification")
    co = importlib.import_module("report_renderer.data.control_objectives")
    en = importlib.import_module("report_renderer.data.engine")
    assert q.card(IDS["A"], IDS["A_V2"], sources=iso_sources) is not None
    assert co.assessment(IDS["A"], IDS["A_V2"], sources=iso_sources) is not None
    pids = {e["pid"] for e in en.evaluations(IDS["A"], IDS["A_V2"], sources=iso_sources)}
    assert IDS["EVAL_A_V2"] in pids and IDS["EVAL_A_V3"] not in pids and IDS["EVAL_A_V1"] not in pids


def test_another_projects_version_reads_nothing_from_this_database(iso_sources):
    """The project scope is the database: Beta's database has no row of Alpha v2, and Alpha's
    database has no row of Beta v1, so every reader answers nothing (the project filter is the database)."""
    q = importlib.import_module("report_renderer.data.qualification")
    co = importlib.import_module("report_renderer.data.control_objectives")
    en = importlib.import_module("report_renderer.data.engine")
    assert q.card(IDS["B"], IDS["A_V2"], sources=iso_sources) is None
    assert co.assessment(IDS["B"], IDS["A_V2"], sources=iso_sources) is None
    assert en.evaluations(IDS["B"], IDS["A_V2"], sources=iso_sources) == []
    assert q.card(IDS["A"], IDS["B_V1"], sources=iso_sources) is None
    assert en.evaluations(IDS["A"], IDS["B_V1"], sources=iso_sources) == []


def test_no_other_projects_data_in_a_report(iso_deps):
    """Beta's ids named in Alpha's layout show nothing of Beta."""
    blocks = [block("test_results"), block("control_answers", checklists=["cl-b"]),
              block("ai_card"), block("control_objectives")]
    html = iso_render(iso_deps, blocks)["html"]
    assert "BETAMARK" not in html


# NotInProject, and a missing database, schema or table.


def test_a_version_of_another_project_is_not_in_project(iso_sources):
    """B_V1 lives in project.system of Beta's database only, so under Alpha it is NotInProject."""
    NotInProject = need("report_renderer.data.scope", "NotInProject")
    pinned_system = need("report_renderer.data.platform", "pinned_system")
    with pytest.raises(NotInProject):
        pinned_system(IDS["A"], IDS["B_V1"], sources=iso_sources)
    with pytest.raises(NotInProject):
        pinned_system(IDS["A"], "deadbeef-0000-4000-8000-00000000dead", sources=iso_sources)


@pytest.fixture
def iso_client(iso_deps):
    from fastapi.testclient import TestClient

    return lazily(lambda: TestClient(need("report_service", "create_app")(deps=iso_deps, token=TOKEN)))


def test_the_service_answers_404_for_a_version_of_another_project(iso_client):
    """/v1/choices and /v1/render answer 404 not_found for Beta's version
    under Alpha (it is not in project.system of Alpha's database)."""
    body = {"project_id": IDS["A"], "system_id": IDS["B_V1"], "block_type": "test_results"}
    assert iso_client.post("/v1/choices", json=body, headers=H).status_code == 404
    snap = snapshot([block("free_text", text="x")])
    snap["system_id"] = IDS["B_V1"]
    r = iso_client.post("/v1/render", json=snap, headers=H)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_the_service_serves_alpha_from_its_database(iso_client):
    """The counterpart: Alpha's own version renders and offers its tools (200)."""
    body = {"project_id": IDS["A"], "system_id": IDS["A_V2"], "block_type": "test_results"}
    r = iso_client.post("/v1/choices", json=body, headers=H)
    assert r.status_code == 200, r.text[:300]
    assert "LangBiTe" in {c["value"] for c in r.json()["tools"]}


def test_a_missing_project_database_gives_empty_for_every_data_block(iso_deps):
    """Gamma has a core.project row and no database: every data block is
    `empty`, none `error`, and the render does not fail."""
    blocks = [block(t) for t in DATA_BLOCKS]
    result = _render_with(iso_deps, blocks, IDS["C"], IDS["C_V1"])
    statuses = {s["block_type"]: s["status"] for s in result["block_statuses"]}
    assert statuses == {t: "empty" for t in DATA_BLOCKS}, statuses


@pytest.mark.parametrize("module,function", [("qualification", "card"), ("control_objectives", "assessment"),
                                             ("engine", "evaluations")])
def test_a_missing_project_database_reads_as_nothing(iso_sources, module, function):
    """The data functions themselves answer nothing (None / []) for a project without a database."""
    fn = getattr(importlib.import_module(f"report_renderer.data.{module}"), function)
    assert fn(IDS["C"], IDS["C_V1"], sources=iso_sources) in (None, [])


def test_a_missing_module_schema_or_table_gives_empty_never_error(iso_deps):
    """Project X's database exists with its version, an empty qualification schema (no tables) and
    no control_objectives or engine schema: every data block is `empty`, never `error`."""
    blocks = [block(t) for t in DATA_BLOCKS]
    result = _render_with(iso_deps, blocks, X, X_V1)
    statuses = {s["block_type"]: s["status"] for s in result["block_statuses"]}
    assert statuses == {t: "empty" for t in DATA_BLOCKS}, statuses


# Every data function takes the project and the version first.


@pytest.mark.parametrize("name", ["platform", "qualification", "control_objectives", "engine", "controls"])
def test_every_data_function_still_takes_project_and_system_first(name):
    """No data function can read without a project."""
    module = importlib.import_module(f"report_renderer.data.{name}")
    public = [f for n, f in inspect.getmembers(module, inspect.isfunction)
              if not n.startswith("_") and f.__module__ == module.__name__]
    assert public
    for f in public:
        assert list(inspect.signature(f).parameters)[:2] == ["project_id", "system_id"], f"{name}.{f.__name__}"


# The golden captures re-run on project databases.


def _golden():
    import test_compat_golden as g  # the goldens and their comparison rules, unchanged

    return g


@pytest.fixture
def iso_gdeps(iso_deps, iso_sources, registry):
    return lazily(lambda: need("report_renderer.context", "Deps")(
        registry=registry, sources=iso_sources, images=need("report_renderer.superset", "NoImageProvider")(),
        clock=lambda: FIXED_NOW, chart_data=None))


@pytest.mark.parametrize("name", ["a_v2_live", "a_v2_live_styled", "m_v2_live_styled"])
def test_golden_with_evaluations_on_project_databases(iso_gdeps, name):
    """As in test_compat_golden: only the Test results section may differ from the golden."""
    g = _golden()
    result = need("report_renderer.document", "render")(g.snapshot_for(g.CASES[name], "preview"), iso_gdeps)
    g._assert_same_except(result["html"], g.golden(name), {g.TEST_RESULTS_IID})
