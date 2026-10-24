"""A run on a local model file is not part of the assessment record.

The engine worker marks it by storing {"local_model": {...}} as the value of the plugin's model input.
Mike's evaluation 2 has runs 721 and 722; the fixture marks the model input of 721, so evaluation 2 is
local. Every other evaluation of the bed is a card run."""
import json

import psycopg
import pytest

from conftest import IDS, need

pytestmark = pytest.mark.db

LOCAL_VALUE = {"local_model": {"file": "scoring.onnx", "sha256": "ab" * 32}}


@pytest.fixture
def local_run(bed):
    db = need("report_bed", "project_db")(IDS["M"])
    with psycopg.connect(bed.su_dsn(db), autocommit=True) as conn:
        before = conn.execute("SELECT value FROM engine.aisc_backend_evaluationinput"
                              " WHERE evaluation_plugin_id = 721 AND name = 'model'").fetchone()[0]
        conn.execute("UPDATE engine.aisc_backend_evaluationinput SET value = %s"
                     " WHERE evaluation_plugin_id = 721 AND name = 'model'", (json.dumps(LOCAL_VALUE),))
        local_pid = conn.execute("SELECT e.pid::text FROM engine.aisc_backend_evaluation e"
                                 " JOIN engine.aisc_backend_evaluationplugin ep ON ep.evaluation_id = e.id"
                                 " WHERE ep.id = 721").fetchone()[0]
        try:
            yield local_pid
        finally:
            conn.execute("UPDATE engine.aisc_backend_evaluationinput SET value = %s"
                         " WHERE evaluation_plugin_id = 721 AND name = 'model'", (json.dumps(before),))


def _evaluations(sources, **kw):
    return need("report_renderer.data.engine", "evaluations")(IDS["M"], IDS["M_V2"], sources=sources, **kw)


def test_selecting_a_local_run_is_refused(sources, local_run):
    refused = need("report_renderer.data.engine", "LocalRunRefused")
    with pytest.raises(refused, match="a local run is not part of the assessment record"):
        _evaluations(sources, pids=[local_run])


def test_a_local_run_is_left_out_of_a_period_or_version_selection(sources, local_run):
    assert local_run not in {e["pid"] for e in _evaluations(sources)}


def test_without_a_local_run_the_same_evaluation_is_selected(sources):
    pids = {e["pid"] for e in _evaluations(sources)}
    assert pids
    assert _evaluations(sources, pids=sorted(pids)), "card runs are selectable by id"
