"""A run's conversation results are never listed row by row. The runs are given by a stand-in for load_runs, on the
bed's project."""
from datetime import datetime

import pytest

from conftest import render_one
from report_renderer.views import EvaluationView, RunsView, RunView
from aisc_report_plugin_interface.tools import ToolRun

pytestmark = pytest.mark.db
MIJKE = {"display_name": "LangBiTe (Mijke)", "name": "LangBiteMijkeEvaluationPlugin", "package_name": "p", "version": "1"}
OTHER = {"display_name": "Mystery Tool", "name": "MysteryPlugin", "package_name": "m", "version": "1"}


def talk(category, community, slot, orgs, register="basic", scenario="P1"):
    d = {"category": category, "community": community, "scenario": scenario, "register": register, "language": "en",
         "repetition": 1, "organisations": orgs, "outcome": "referral" if orgs else "no referral"}
    if slot is not None:
        d["slot"] = slot
    return {"name": "Conversation", "metric": "Conversation", "score": 1.0 if orgs else 0.0, "dimensions": d}


def conversations(category, orgs_of_person):
    rows = []
    for register in ("basic", "advanced", "broken"):
        rows.append(talk("BASELINE", "-", None, "A", register=register))
        for slot, (person, orgs) in enumerate(orgs_of_person):
            rows.append(talk(category, person, slot, orgs, register=register))
    return rows


def view_of(*runs):
    """runs: (tool, target label, created_at, measurements), oldest first."""
    evaluations = []
    for i, (tool, label, when, measurements) in enumerate(runs):
        run = ToolRun(evaluation={"pid": f"e{i}", "status": "Done", "created_at": when},
                      evaluation_plugin={"pid": f"p{i}", "name": "", "status": "Done", "plugin_config_id": i},
                      tool=tool, components=(), observations=(), measurements=tuple(measurements), artifacts=(),
                      target={"key": label, "kind": "component", "component_kind": "model", "label": label,
                              "card_version": 1, "status": "current"})
        evaluations.append(EvaluationView(
            evaluation={"pid": f"e{i}", "status": "Done", "created_at": datetime.fromisoformat(when)}, unmatched=[],
            unmatched_count=0,
            runs=[RunView(tool=tool, components=[], status="Done", run=run, artifacts=[])]))
    return RunsView(evaluations=evaluations, unversioned=0)


@pytest.fixture
def given(monkeypatch):
    def put(*runs):
        monkeypatch.setattr("report_renderer.blocks.test_results.load_runs", lambda *a, **k: view_of(*runs))
    return put


AGE = [("18", "A"), ("40", "A"), ("70", "B")]


def test_by_evaluation_lists_the_other_results_without_the_conversation_rows(deps, given):
    given((MIJKE, "OpenAI", "2026-11-01T10:00:00",
           conversations("AGE", AGE) + [{"name": "Overall Pass Rate", "metric": "Overall Pass Rate", "score": 0.0}]))
    text, status, node, _ = render_one(deps, "test_results")
    cells = [td.get_text(strip=True) for td in node.find_all("td")]
    assert "Overall Pass Rate" in cells and "Conversation" not in cells
    assert "12 conversation results from 1 run are not listed" in text + " ".join(status["notices"])


def test_conversation_results_left_out_are_said_once_with_their_total(deps, given):
    given((MIJKE, "OpenAI", "2026-11-01T10:00:00", conversations("AGE", AGE)),
          (MIJKE, "Local", "2026-11-01T11:00:00", conversations("AGE", AGE)))
    _, status, _, _ = render_one(deps, "test_results")
    said = [n for n in status["notices"] if "conversation results" in n]
    assert said == ["24 conversation results from 2 runs are not listed."]
