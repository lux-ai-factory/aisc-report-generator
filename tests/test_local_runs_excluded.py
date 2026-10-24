"""A run on a local model file is not part of the assessment record.

The engine worker marks it by storing {"local_model": {...}} as the value of the plugin's model input.
Mike's evaluation 72 holds two runs: 721 (LangBiTe) and 722 (StrongREJECT); evaluation 71 holds run 711
(StrongREJECT) alone. Exclusion is per plugin run: a card run stays in a report beside a local run of the
same evaluation."""
import json

import psycopg
import pytest

from conftest import IDS, need
from report_renderer.selection import Selection

pytestmark = pytest.mark.db

LOCAL_VALUE = {"local_model": {"file": "scoring.onnx", "sha256": "ab" * 32}}
EVAL_MIXED, EVAL_ALONE = "f2e00000-0000-4000-8000-000000000072", "f2e00000-0000-4000-8000-000000000071"


def _connect(bed):
    db = need("report_bed", "project_db")(IDS["M"])
    return psycopg.connect(bed.su_dsn(db), autocommit=True)


def _mark(bed, run_condition, value=LOCAL_VALUE):
    """Set the model input of the runs `run_condition` (SQL on evaluationplugin ep) selects to `value`;
    returns the undo."""
    conn = _connect(bed)
    saved = conn.execute("SELECT i.id, i.value FROM engine.aisc_backend_evaluationinput i"
                         " JOIN engine.aisc_backend_evaluationplugin ep ON ep.id = i.evaluation_plugin_id"
                         f" WHERE i.name = 'model' AND ({run_condition})").fetchall()
    for iid, _ in saved:
        conn.execute("UPDATE engine.aisc_backend_evaluationinput SET value = %s WHERE id = %s",
                     (json.dumps(value), iid))

    def undo():
        for iid, value in saved:
            conn.execute("UPDATE engine.aisc_backend_evaluationinput SET value = %s WHERE id = %s",
                         (json.dumps(value), iid))
        conn.close()
    return undo


@pytest.fixture
def local_langbite_run(bed):
    undo = _mark(bed, "ep.id = 721")
    yield
    undo()


@pytest.fixture
def local_langbite_run_untagged(bed):
    """Run 721 is local and neither observation of evaluation 72 names its run (an older engine left the
    tool empty), so nothing tells whose they are."""
    undo = _mark(bed, "ep.id = 721")
    conn = _connect(bed)
    saved = conn.execute("SELECT id, tool FROM engine.aisc_backend_observation WHERE evaluation_id = 72").fetchall()
    conn.execute("UPDATE engine.aisc_backend_observation SET tool = '' WHERE evaluation_id = 72")
    yield
    for oid, tool in saved:
        conn.execute("UPDATE engine.aisc_backend_observation SET tool = %s WHERE id = %s", (tool, oid))
    conn.close()
    undo()


@pytest.fixture
def local_only_evaluation(bed):
    undo = _mark(bed, "ep.id = 711")
    yield
    undo()


@pytest.fixture
def every_langbite_run_local(bed):
    undo = _mark(bed, "ep.plugin_config_id = 6")
    yield
    undo()


def _engine(name):
    return need("report_renderer.data.engine", name)


def _evaluations(sources, **kw):
    return _engine("evaluations")(IDS["M"], IDS["M_V2"], sources=sources, **kw)


def _mixed(sources):
    (ev,) = [e for e in _evaluations(sources) if e["pid"] == EVAL_MIXED]
    return ev


def test_selecting_an_evaluation_with_only_local_runs_is_refused(sources, local_only_evaluation):
    with pytest.raises(_engine("LocalRunRefused"), match="a local run is not part of the assessment record"):
        _evaluations(sources, pids=[EVAL_ALONE])


def test_an_evaluation_with_only_local_runs_is_left_out_of_a_selection(sources, local_only_evaluation):
    assert EVAL_ALONE not in {e["pid"] for e in _evaluations(sources, selection=Selection(other_versions=True))}


def test_card_runs_are_selectable_by_pid(sources):
    assert [e["pid"] for e in _evaluations(sources, pids=[EVAL_MIXED])] == [EVAL_MIXED]


def test_an_evaluation_with_a_local_and_a_card_run_stays(sources, local_langbite_run):
    ev = _mixed(sources)
    assert [e["pid"] for e in _evaluations(sources, pids=[EVAL_MIXED])] == [EVAL_MIXED]
    runs = _engine("runs")(IDS["M"], IDS["M_V2"], sources=sources, evaluation_ids=[ev["id"]])
    assert [r["id"] for r in runs] == [722]


def test_the_local_runs_inputs_artifacts_details_and_observations_are_left_out(sources, local_langbite_run):
    ev = _mixed(sources)
    args = (IDS["M"], IDS["M_V2"])
    assert {i["evaluation_plugin_id"] for i in _engine("inputs")(*args, sources=sources, run_ids=[721, 722])} == {722}
    artifacts = _engine("artifacts")(*args, sources=sources, run_ids=[721, 722])
    assert [(a["evaluation_plugin_id"], a["name"]) for a in artifacts] == [(722, "strongreject_per_prompt.csv")]
    details = _engine("run_details")(*args, sources=sources, evaluation_ids=[ev["id"]])
    assert [d["name"] for d in details] == ["StrongRejectPlugin"]
    obs = _engine("observations")(*args, sources=sources, evaluation_ids=[ev["id"]])
    assert [o["tool"] for o in obs] == ["aisc-plugin-strongreject::StrongRejectPlugin (v0.1.0)"]
    ms = _engine("measurements")(*args, sources=sources, observation_ids=[7201, 7202])
    assert {m["observation_id"] for m in ms} == {7202}


def test_the_choice_lists_leave_out_a_tool_that_only_ran_locally(sources, every_langbite_run_local):
    args = (IDS["M"], IDS["M_V2"])
    tools = {r["value"] for r in _engine("tool_choices")(*args, sources=sources)}
    pairs = {r["tool"] for r in _engine("metric_pairs")(*args, sources=sources)}
    assert not any("langbite" in t.lower() for t in tools | pairs)
    assert tools and pairs


def test_the_choice_lists_still_offer_card_tools(sources):
    args = (IDS["M"], IDS["M_V2"])
    assert any("langbite" in r["value"].lower() for r in _engine("tool_choices")(*args, sources=sources))



def test_untagged_observations_of_an_evaluation_with_a_local_run_are_left_out(sources, local_langbite_run_untagged):
    ev = _mixed(sources)
    args = (IDS["M"], IDS["M_V2"])
    assert _engine("observations")(*args, sources=sources, evaluation_ids=[ev["id"]]) == []


def test_the_card_run_beside_a_local_run_does_not_take_its_untagged_observations(sources, local_langbite_run_untagged):
    pairs = {(r["tool"], r["metric"]) for r in _engine("metric_pairs")(IDS["M"], IDS["M_V2"], sources=sources)}
    assert ("StrongREJECT", "Overall Pass Rate") not in pairs
    assert ("StrongREJECT", "StrongREJECT Harmfulness") in pairs

