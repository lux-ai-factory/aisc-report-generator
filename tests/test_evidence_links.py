"""Evidence in the report.

- The report lists the objectives selected in step 2 (control_objectives.objective_selection, one row
  per assessment), not every mapped one. A version whose assessment has no selection, or a database
  without the table, lists every mapped one.
- The links come from step 4 (the platform's evidence.link), which the composer copies into the
  snapshot's coverage_links; a test is named there by its plugin's package name
  ("aisc-plugin-langbite"), which matches the plugin's runs like its display name does.

The bed's seed has no selection table, so the fixture below makes it in Mike's database for one test
and removes it after. Mike v2's mapping links R1.1, R2.1, R4.1 and R5.1.
"""
import psycopg
import pytest

from conftest import IDS, block, need, section
from test_v2_coverage_map import statuses
from v2_block_helpers import render_snapshot, v2_snapshot

pytestmark = pytest.mark.db

SELECTED = ["R1.1", "R4.1"]


@pytest.fixture
def selection(bed):
    db = need("report_bed", "project_db")(IDS["M"])
    with psycopg.connect(bed.su_dsn(db), autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS control_objectives.objective_selection")
        conn.execute("CREATE TABLE control_objectives.objective_selection (project_id varchar(32) PRIMARY KEY,"
                     " objective_ids text[] NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())")
        conn.execute("GRANT SELECT ON control_objectives.objective_selection TO report_ro")
        assessment = conn.execute("SELECT id FROM control_objectives.project WHERE system_id = %s",
                                  (IDS["M_V2"],)).fetchone()[0]
        conn.execute("INSERT INTO control_objectives.objective_selection (project_id, objective_ids) VALUES (%s, %s)",
                     (assessment, SELECTED))
        try:
            yield assessment
        finally:
            conn.execute("DROP TABLE IF EXISTS control_objectives.objective_selection")


def _statuses(deps, block_type, links, **options):
    b = block(block_type, **options)
    result = render_snapshot(deps, v2_snapshot([b], coverage_links=links))
    return statuses(section(result["html"], b["instance_id"]))


def test_the_control_objectives_block_lists_the_selected_objectives(deps, selection):
    assert set(_statuses(deps, "control_objectives", [])) == set(SELECTED)


def test_the_summary_lists_the_selected_objectives(deps, selection):
    assert set(_statuses(deps, "summary_coverage", [])) == set(SELECTED)


def test_an_empty_selection_lists_nothing(deps, selection, bed):
    db = need("report_bed", "project_db")(IDS["M"])
    with psycopg.connect(bed.su_dsn(db), autocommit=True) as conn:
        conn.execute("UPDATE control_objectives.objective_selection SET objective_ids = '{}'")
    assert _statuses(deps, "control_objectives", []) == {}


def test_without_a_selection_the_mapped_objectives_are_listed(deps):
    assert set(_statuses(deps, "control_objectives", [])) == {"R1.1", "R2.1", "R4.1", "R5.1"}


def test_a_link_names_a_test_by_its_package(deps):
    links = [{"objective_id": "R1.1", "tests": ["aisc-plugin-langbite"], "checklists": []}]
    assert _statuses(deps, "control_objectives", links)["R1.1"] == "evidence"
