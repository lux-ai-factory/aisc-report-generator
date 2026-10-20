"""A run's target in the report.

Every evaluation names its target, the AI system or one component of its AI card, as an engine input
named `target` whose component is a platform-kept mirror (target.target.engine_component). The bed's
seed has no targets, so the fixture below adds them to Mike's database for one test and removes them
after (the seed lives in the superproject, scripts/tests/fixtures/report):

  target.target (Mike's cards: v1, v2; the latest is 2)
    system                  "Example Assistant"          mirror T_SYS   first 1, last 2
    component:<SCORING>     model            "Scoring model"  mirror T_SCORE first 1, last 2  (current)
    component:<TRAINING>    training_data    "Training data"  mirror T_TRAIN first 1, last 1  (stale)
  inputs named `target`
    run 721 (evaluation 2, LangBiTe)       -> Scoring model
    run 722 (evaluation 2, StrongREJECT)   -> the system
    run 731 (evaluation 3, Promptfoo)      -> Training data (stale)
    run 741 (evaluation 4, Promptfoo)      -> "Example Assistant endpoint", an ordinary component: not a target
    run 711 (evaluation 1, StrongREJECT)   -> none: made before targets
    run 701 (version 1, LangBiTe)          -> Scoring model, card v1
"""
import psycopg
import pytest

from conftest import IDS, need, text
from v2_block_helpers import one

pytestmark = pytest.mark.db

SCORING = "5c000000-0000-4000-8000-000000000001"
TRAINING = "5c000000-0000-4000-8000-000000000002"
T_SYS, T_SCORE, T_TRAIN = ("f0ec0000-0000-4000-8000-0000000000a1", "f0ec0000-0000-4000-8000-0000000000a2",
                           "f0ec0000-0000-4000-8000-0000000000a3")
MIRRORS = [(961, T_SYS, "Example Assistant"), (962, T_SCORE, "Scoring model"), (963, T_TRAIN, "Training data")]
#: evaluationinput id -> (run id, component id); component 6 is the seed's "Example Assistant endpoint"
TARGET_INPUTS = {9601: (721, 962), 9602: (722, 961), 9603: (731, 963), 9604: (741, 6), 9605: (701, 962)}


@pytest.fixture
def targets(bed):
    db = need("report_bed", "project_db")(IDS["M"])
    with psycopg.connect(bed.su_dsn(db), autocommit=True) as conn:
        _clean(conn)
        with conn.transaction():
            for cid, pid, name in MIRRORS:
                conn.execute("INSERT INTO engine.aisc_backend_aicomponent (id, pid, name, description, created_at,"
                             " data, storage_container, component_type, json_value, system_id)"
                             " VALUES (%s, %s, %s, '', now(), '', '', 'resource', '{}', 6)", (cid, pid, name))
            conn.execute(
                "INSERT INTO target.target (key, kind, component_kind, label, first_card_number, last_card_number,"
                " engine_component) VALUES ('system', 'system', NULL, 'Example Assistant', 1, 2, %s),"
                " (%s, 'component', 'model', 'Scoring model', 1, 2, %s),"
                " (%s, 'component', 'training_data', 'Training data', 1, 1, %s)",
                (T_SYS, f"component:{SCORING}", T_SCORE, f"component:{TRAINING}", T_TRAIN))
            for iid, (run, cid) in TARGET_INPUTS.items():
                conn.execute("INSERT INTO engine.aisc_backend_evaluationinput (id, pid, name, description, created_at,"
                             " value, component_id, evaluation_plugin_id)"
                             " VALUES (%s, gen_random_uuid(), 'target', '', now(), '{}', %s, %s)", (iid, cid, run))
        try:
            yield
        finally:
            _clean(conn)


def _clean(conn):
    with conn.transaction():
        conn.execute("DELETE FROM engine.aisc_backend_evaluationinput WHERE id = ANY(%s)", (list(TARGET_INPUTS),))
        conn.execute("DELETE FROM engine.aisc_backend_aicomponent WHERE id = ANY(%s)", ([m[0] for m in MIRRORS],))
        conn.execute("DELETE FROM target.target")


def _runs(deps, selection=None, **kw):
    ctx = need("report_renderer.context", "context_for")(IDS["M"], IDS["M_V2"], deps=deps, mode="preview")
    if selection is not None:
        import dataclasses

        from report_renderer.selection import Selection

        ctx = dataclasses.replace(ctx, report=dataclasses.replace(ctx.report, selection=Selection(**selection)))
    view = need("report_renderer.views", "load_runs")(ctx, statuses=None, **kw)
    return {rv.run.evaluation_plugin["pid"][-3:]: rv.run for ev in view.evaluations for rv in ev.runs}


def _runs_of(node):
    return {r.find("h4").get_text(" ").strip() + "@" + str(i): text(r)
            for i, r in enumerate(node.find_all("div", class_="run"))}


# The data layer.

def test_inputs_carry_the_input_name_and_the_component_pid(sources, targets):
    rows = need("report_renderer.data.engine", "inputs")(IDS["M"], IDS["M_V2"], sources=sources, run_ids=[721])
    by_name = {r["input_name"]: r for r in rows}
    assert set(by_name) == {"model", "target"}
    assert by_name["target"]["component_pid"] == T_SCORE and by_name["model"]["name"] == "Example Assistant endpoint"


def test_a_component_target(deps, targets):
    assert dict(_runs(deps)["721"].target) == {
        "key": f"component:{SCORING}", "kind": "component", "component_kind": "model", "label": "Scoring model",
        "card_version": 2, "status": "current"}


def test_a_system_target(deps, targets):
    assert dict(_runs(deps)["722"].target) == {
        "key": "system", "kind": "system", "component_kind": None, "label": "Example Assistant", "card_version": 2,
        "status": "current"}


def test_a_component_no_longer_on_the_latest_card_is_stale(deps, targets):
    t = _runs(deps)["731"].target
    assert t["label"] == "Training data" and t["component_kind"] == "training_data" and t["status"] == "stale"


def test_a_target_input_that_is_not_a_mirror(deps, targets):
    assert dict(_runs(deps)["741"].target) == {
        "key": None, "kind": None, "component_kind": None, "label": "Example Assistant endpoint", "card_version": 2,
        "status": "not a target"}


def test_a_run_made_before_targets_has_none(deps, targets):
    runs = _runs(deps)
    assert runs["711"].target is None and runs["751"].target is None


def test_without_any_target_row_every_run_has_none(deps):
    assert all(r.target is None for r in _runs(deps).values())


def test_the_card_version_is_the_evaluations(deps, targets):
    t = _runs(deps, selection={"other_versions": True})["701"].target
    assert t["label"] == "Scoring model" and t["card_version"] == 1 and t["status"] == "current"


def test_the_target_input_is_still_a_component(deps, targets):
    comps = [c["name"] for c in _runs(deps)["721"].components]
    assert comps == ["Example Assistant endpoint", "Scoring model"]


# The block: rendering.

def test_each_run_names_its_target(deps, targets):
    _, _, node, _ = one(deps, "test_results", statuses=["Done", "Failed"])
    runs = list(_runs_of(node).values())
    joined = " || ".join(runs)
    assert "Tested: Scoring model (Model, AI card v2)" in joined
    assert "Tested: System Example Assistant (AI card v2)" in joined
    assert "Tested: Training data (Training data, AI card v2), not on the latest AI card" in joined
    assert "Tested: Example Assistant endpoint, neither the system nor a component" in joined
    assert sum("Tested: not recorded" in r for r in runs) == 2      # runs 711 and 751
    assert "Target" not in joined


def test_the_components_line_is_kept(deps, targets):
    t, *_ = one(deps, "test_results")
    assert "Components: Example Assistant endpoint (model), Scoring model (resource)" in t


def test_without_targets_every_run_says_not_recorded(deps):
    _, _, node, _ = one(deps, "test_results", statuses=["Done", "Failed"])
    runs = list(_runs_of(node).values())
    assert runs and all("Tested: not recorded" in r for r in runs)


def test_the_target_line_is_escaped(deps, targets, bed):
    db = need("report_bed", "project_db")(IDS["M"])
    with psycopg.connect(bed.su_dsn(db), autocommit=True) as conn:
        conn.execute("UPDATE target.target SET label = '<b>x</b>' WHERE key = 'system'")
    _, _, node, result = one(deps, "test_results")
    assert "<b>x</b>" not in result["html"] and "Tested: System <b>x</b>" in text(node)


# The block: the target filter.

def test_the_target_option_is_declared_like_the_tools_filter(deps):
    cls = deps.registry.block("test_results")
    props = cls.full_options_schema()["properties"]
    assert "targets" in props, "missing feature: option targets of block test_results"
    assert props["targets"]["title"] == "Systems and components" and props["targets"]["description"]
    assert "target" not in props["targets"]["description"]
    assert props["tools"]["title"] == "Tests" and props["tools"]["description"] == "Which tests to show."
    assert props["targets"].get("x-aisc-reference") is True
    assert cls.full_default_options()["targets"] == "all"
    assert cls.options_problems({**cls.full_default_options(), "targets": ["system"]}) == []
    assert cls.options_problems({**cls.full_default_options(), "targets": [""]})


def test_filter_by_target_key(deps, targets):
    _, _, node, _ = one(deps, "test_results", statuses=["Done", "Failed"], targets=[f"component:{SCORING}"])
    assert [h.split("@")[0] for h in _runs_of(node)] == ["LangBiTe"]
    assert [" ".join(h.get_text(" ").split()) for h in node.find_all("h3")] == [
        "Evaluation 2: LangBiTe, StrongREJECT"]


def test_filter_by_target_label(deps, targets):
    _, _, node, _ = one(deps, "test_results", statuses=["Done", "Failed"], targets=["Example Assistant", "Training data"])
    assert [h.split("@")[0] for h in _runs_of(node)] == ["StrongREJECT", "Promptfoo"]


def test_filter_all_is_today(deps, targets):
    t1, *_ = one(deps, "test_results", statuses=["Done", "Failed"])
    t2, *_ = one(deps, "test_results", statuses=["Done", "Failed"], targets="all")
    assert t1 == t2


def test_a_filter_matching_nothing_leaves_the_block_empty(deps, targets):
    _, st, node, _ = one(deps, "test_results", targets=["No such target"])
    assert st["status"] == "empty" and not node.find_all("div", class_="run")


def test_target_choices(deps, targets):
    ctx = need("report_renderer.context", "context_for")(IDS["M"], IDS["M_V2"], deps=deps, mode="preview")
    choices = deps.registry.block("test_results")().choices(ctx, "targets")
    assert choices == [
        {"value": "system", "label": "System: Example Assistant"},
        {"value": f"component:{SCORING}", "label": "Scoring model (Model)"},
        {"value": f"component:{TRAINING}", "label": "Training data (Training data)"},
    ]
