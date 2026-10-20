"""Fixtures of the renderer tests.

The database tests run on one throwaway postgres:15-alpine container per session, built by the
superproject's `scripts/lib/report_bed_isolated.py` (found through AISC_INSTALL_DIR, see below). It
loads the report bed's seed (`report_bed.py`: init SQL, platform migrations, schema dumps of the module
schemas, a fixed seed) and moves it into one database per project: `platform` keeps core.project and
core.project_member only; each project's versions (project.system) and module rows (qualification,
control_objectives, engine, controls) are in its own database project_<hex>. Every seeded project has
a database here (`no_database=frozenset()`), gamma too: it holds gamma's one version C_V1 and empty
module tables, so gamma stays "another project alice edits". A project with no database at all is
tested by tests/test_isolation_project_databases.py on its own bed. The renderer connects as
`report_ro`. The bed never uses the host's port 5432: every DSN variable is checked before it starts.

The API the tests use of `report_renderer`:

    report_renderer.data.Sources(platform_dsn, superset_dsn, project_db_template,
                                 airo_vocab_path, objectives_csv_path, superset_url=None)
    report_renderer.data.Sources.from_env(env)
    report_renderer.registry.build_registry(builtins=True, entry_points=None, plugin_dirs=())
        -> Registry(.block(type_id), .block_types(), .tool_for(plugin_row), .register_block(cls, origin),
                    .register_tool(cls, origin))
    report_renderer.superset.NoImageProvider(), FakeImageProvider(png), SupersetScreenshotProvider(...),
        FakeChartData(columns, rows), NoChartData(), image_provider_from_env(env)
    report_renderer.context.Deps(registry, sources, images, clock, chart_data=None)
    report_renderer.document.render(snapshot, deps) -> {"html" | "pdf_base64"+"sha256", "block_statuses"}
    report_service.create_app(deps=..., token=...) -> FastAPI app
"""
from __future__ import annotations

import importlib
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

# As a submodule of aisc (apps/report-generator) the superproject is two folders up; as a standalone
# checkout it is the sibling ~/aisc-definitive. AISC_INSTALL_DIR overrides both.
_HERE = Path(__file__).resolve()
_DEFAULT_INSTALL = _HERE.parents[3] if (_HERE.parents[3] / "scripts/lib/report_bed.py").exists() else _HERE.parents[2] / "aisc-definitive"
AISC_INSTALL = Path(os.environ.get("AISC_INSTALL_DIR", _DEFAULT_INSTALL))
sys.path.insert(0, str(AISC_INSTALL / "scripts/lib"))

import report_bed  # noqa: E402

try:
    import report_bed_isolated  # noqa: E402
except ModuleNotFoundError:  # no report_bed_isolated.py: the database tests fail and say why
    report_bed_isolated = None

IDS = report_bed.IDS
FOREIGN_MARKERS = report_bed.FOREIGN_MARKERS
FIXED_NOW = datetime(2026, 9, 20, 10, 30, tzinfo=timezone.utc)
#: a 1x1 PNG, what the fake Superset returns
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def need(module: str, name: str):
    """A public name of the code under test, or a FAILED test saying which one is missing."""
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name and (exc.name == module or module.startswith(exc.name + ".")):
            pytest.fail(f"missing feature: module {module}", pytrace=False)
        raise
    value = getattr(mod, name, None)
    if value is None:
        pytest.fail(f"missing feature: {module}.{name}", pytrace=False)
    return value


class Missing:
    """Stands in for a fixture value while the code under test is missing: using it FAILS the
    test (in its body) instead of erroring its setup."""

    def __init__(self, message):
        self._message = message

    def __getattr__(self, name):
        pytest.fail(self._message, pytrace=False)

    def __call__(self, *a, **k):
        pytest.fail(self._message, pytrace=False)


def lazily(make):
    try:
        return make()
    except pytest.fail.Exception as exc:
        return Missing(str(exc))


# The database bed.


@pytest.fixture(scope="session")
def bed():
    if report_bed_isolated is None:
        pytest.fail(f"AISC_INSTALL_DIR ({AISC_INSTALL}) must point at an install with"
                    " scripts/lib/report_bed_isolated.py (the superproject, ~/aisc-definitive)", pytrace=False)
    report_bed.check_dsn_env()
    b = report_bed_isolated.build_isolated("renderer", modules=True, no_database=frozenset())
    # the dashboard adds this column when it starts (superset_config.py); the bed's schema dump predates it
    b.psql("superset", "ALTER TABLE aisc_comment ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP")
    controls_keep_closed_answers(b)
    yield b
    b.stop()


#: What apps/controls' migrations 20261018000000 and 20261018000100 add, which the bed's schema dump of
#: controls predates: each answer keeps its question as a closed submission answered it, the submission the
#: template revision, and an answer stays when its question is removed (questionId NULL).
CONTROLS_CLOSED_ANSWERS_SQL = """
DO $$
BEGIN
  IF to_regclass('controls.submission_answer') IS NOT NULL THEN
    ALTER TABLE controls.submission_answer
      ADD COLUMN IF NOT EXISTS question_text TEXT, ADD COLUMN IF NOT EXISTS question_article TEXT,
      ADD COLUMN IF NOT EXISTS question_category TEXT, ADD COLUMN IF NOT EXISTS question_order INTEGER,
      ALTER COLUMN "questionId" DROP NOT NULL;
    ALTER TABLE controls.submission ADD COLUMN IF NOT EXISTS questions_version INTEGER;
  END IF;
END $$;
"""


def controls_keep_closed_answers(b):
    """CONTROLS_CLOSED_ANSWERS_SQL in every project database of the bed."""
    names = b.scalar("platform", "SELECT string_agg(datname, ' ') FROM pg_database WHERE left(datname, 8) = 'project_'")
    for name in (names or "").split():
        b.psql(name, CONTROLS_CLOSED_ANSWERS_SQL)


@pytest.fixture(scope="session")
def sources(bed):
    return lazily(lambda: _sources(bed.env()))


def _sources(env):
    Sources = need("report_renderer.data", "Sources")
    return Sources(
        platform_dsn=env["REPORT_PLATFORM_DATABASE_URL"],
        superset_dsn=env["REPORT_SUPERSET_DATABASE_URL"],
        project_db_template=env["REPORT_PROJECT_DB_URL"],
        airo_vocab_path=env["REPORT_AIRO_VOCAB_PATH"],
        objectives_csv_path=env["REPORT_OBJECTIVES_CSV_PATH"],
        superset_url="http://superset.invalid:8188",
    )


class RecordingImages:
    """The fake Superset rendering: a fixed PNG, and a record of what was asked."""

    def __init__(self, png=PNG, fail=None, delay=0.0):
        import threading

        self.png, self.fail, self.delay = png, fail, delay
        self.calls = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def image(self, chart_id, width, height):
        import time

        with self._lock:
            self.calls.append((chart_id, width, height))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            if self.fail:
                raise self.fail
            return self.png
        finally:
            with self._lock:
                self.active -= 1


@pytest.fixture
def images():
    return RecordingImages()


@pytest.fixture
def registry():
    return lazily(lambda: need("report_renderer.registry", "build_registry")())


@pytest.fixture
def make_deps(sources, registry, images):
    def make(**over):
        Deps = need("report_renderer.context", "Deps")
        kw = dict(registry=registry, sources=sources, images=images, clock=lambda: FIXED_NOW, chart_data=None)
        kw.update(over)
        return Deps(**kw)

    return lambda **over: lazily(lambda: make(**over))


@pytest.fixture
def deps(make_deps):
    return make_deps()


# Snapshots and reading the HTML.


def block(block_type: str, **options) -> dict:
    return {"instance_id": str(uuid.uuid4()), "block_type": block_type, "options": options}


def snapshot(blocks, project="A", system="A_V2", mode="preview", requested_by="alice",
             name="Quarterly report", revision=4, selection=None) -> dict:
    snap = {
        "project_id": IDS[project],
        "system_id": IDS[system],
        "layout": {"id": "11111111-1111-4111-8111-111111111111", "name": name, "revision": revision},
        "blocks": blocks,
        "mode": mode,
        "requested_by": requested_by,
    }
    if selection is not None:
        snap["snapshot_version"] = 3
        snap["selection"] = selection
    return snap


def window(start=None, end=None, *, other_versions=False, compare_to=None) -> dict:
    """A report's selection: runs created in [start, end), UTC."""
    def iso(v):
        return f"{v}:00+00:00" if v and len(v) == 16 else (f"{v}T00:00:00+00:00" if v and len(v) == 10 else v)

    return {"period_from": iso(start), "period_to": iso(end), "other_versions": other_versions,
            "compare_to": compare_to}


def render(deps, blocks, **kw) -> dict:
    return need("report_renderer.document", "render")(snapshot(blocks, **kw), deps)


def soup(html: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


def section(html: str, instance_id: str):
    """The <section> of one block instance, or a failed assertion."""
    found = soup(html).find("section", id=f"block-{instance_id}")
    assert found is not None, f"no section block-{instance_id} in the document"
    return found


def text(node) -> str:
    return " ".join(node.get_text(" ").split())


def status_of(result: dict, instance_id: str) -> dict:
    for s in result["block_statuses"]:
        if s["instance_id"] == instance_id:
            return s
    raise AssertionError(f"no status for {instance_id}")


def render_one(deps, block_type, project="A", system="A_V2", mode="preview", selection=None, **options):
    """Render a layout of one block; returns (section text, status entry, section node, result)."""
    b = block(block_type, **options)
    result = render(deps, [b], project=project, system=system, mode=mode, selection=selection)
    node = section(result["html"], b["instance_id"])
    return text(node), status_of(result, b["instance_id"]), node, result


def assert_no_foreign_data(html: str, markers=FOREIGN_MARKERS):
    """Assert that nothing of another version or project is shown."""
    leaked = [m for m in markers if m in html]
    assert not leaked, f"data of another version or project in the report: {leaked}"
