"""The Control objectives block marks the priority objectives with their priority score.

The priority objectives are the ones step 2 stores in `control_objectives.objective_selection.priority_ids`
(its default rule with the assessor's choices over it). The score is computed here as in step 2: the sum of
the ratings of the rated risks linked to the objective; a risk with a part unrated counts nothing.

Mike v2 (seed_tools.sql): R-1 (5 x 4 = 20) -> R1.1, R-2 (impact only) -> R2.1, R-3 (1 x 2 = 2) -> R4.1,
R-4 not rated -> R5.1. The bed's schema has no objective_selection table; the fixtures make one.
"""
import psycopg
import pytest

from conftest import IDS, need
from v2_block_helpers import one

pytestmark = pytest.mark.db

SELECTED = ["R1.1", "R2.1", "R4.1", "R5.1"]


def _connect(bed):
    db = need("report_bed", "project_db")(IDS["M"])
    return psycopg.connect(bed.su_dsn(db), autocommit=True)


def _selection(bed, *, priority_ids):
    """objective_selection for Mike v2's assessment, with a priority_ids column when priority_ids is not
    None; returns the undo."""
    conn = _connect(bed)
    column = ", priority_ids text[]" if priority_ids is not None else ""
    conn.execute("CREATE TABLE control_objectives.objective_selection"
                 f" (project_id varchar(32) PRIMARY KEY, objective_ids text[]{column})")
    conn.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'report_ro') THEN"
                 " GRANT SELECT ON control_objectives.objective_selection TO report_ro; END IF; END $$")
    (assessment,) = conn.execute("SELECT id FROM control_objectives.project WHERE system_id = %s",
                                 (IDS["M_V2"],)).fetchone()
    if priority_ids is None:
        conn.execute("INSERT INTO control_objectives.objective_selection VALUES (%s, %s)", (assessment, SELECTED))
    else:
        conn.execute("INSERT INTO control_objectives.objective_selection VALUES (%s, %s, %s)",
                     (assessment, SELECTED, priority_ids))

    def undo():
        conn.execute("DROP TABLE control_objectives.objective_selection")
        conn.close()
    return undo


@pytest.fixture
def priority_r11_and_r41(bed):
    undo = _selection(bed, priority_ids=["R1.1", "R4.1"])
    yield
    undo()


@pytest.fixture
def selection_without_priority(bed):
    undo = _selection(bed, priority_ids=None)
    yield
    undo()


def _priority_ids(sources):
    return need("report_renderer.data.control_objectives", "priority_ids")(IDS["M"], IDS["M_V2"], sources=sources)


def test_the_priority_objectives_are_read_from_the_selection(sources, priority_r11_and_r41):
    assert _priority_ids(sources) == ["R1.1", "R4.1"]


def test_no_priority_objectives_without_the_column(sources, selection_without_priority):
    assert _priority_ids(sources) == []


def test_no_priority_objectives_without_the_selection(sources):
    assert _priority_ids(sources) == []


def _objective(node, oid):
    return " ".join(node.find(attrs={"data-objective": oid}).get_text(" ").split())


def test_each_priority_objective_is_marked_with_its_score(deps, priority_r11_and_r41):
    _, _, node, _ = one(deps, "control_objectives")
    assert "Priority objective, score 20" in _objective(node, "R1.1")
    assert "Priority objective, score 2" in _objective(node, "R4.1")
    assert "Priority objective" not in _objective(node, "R2.1") + _objective(node, "R5.1")


def test_a_priority_objective_is_marked_under_its_risks(deps, priority_r11_and_r41):
    _, _, node, _ = one(deps, "control_objectives", group_by="risk")
    risk = " ".join(node.find(attrs={"data-risk": "R-1"}).get_text(" ").split())
    assert "R1.1" in risk and "Priority objective, score 20" in risk
    risk = " ".join(node.find(attrs={"data-risk": "R-2"}).get_text(" ").split())
    assert "R2.1" in risk and "Priority objective" not in risk


def test_no_marks_when_step_2_stores_no_priority(deps, selection_without_priority):
    t, *_ = one(deps, "control_objectives")
    assert "Priority objective" not in t


def test_no_marks_without_a_selection(deps):
    t, *_ = one(deps, "control_objectives")
    assert "Priority objective" not in t
