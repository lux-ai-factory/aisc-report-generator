"""Coverage when a tool renderer's verdict() raises: the objective stays "evidence",
and the failure is logged with an error ref and its traceback, as Test results logs a failing render()."""
import logging
from types import SimpleNamespace

from report_renderer import coverage
from report_renderer.views import EvaluationView, RunsView, RunView


class Raising:
    def verdict(self, run):
        raise RuntimeError("unexpected measurement")


def test_a_verdict_that_raises_is_logged_with_a_ref(monkeypatch, caplog):
    tool = {"display_name": "LangBiTe", "name": "langbite", "package_name": "aisc-plugin-langbite"}
    run = RunView(tool=tool, components=[], status="Done", run=SimpleNamespace(), artifacts=[])
    view = RunsView(evaluations=[EvaluationView(evaluation={"version_number": 2}, runs=[run], unmatched=[],
                                                unmatched_count=0)], unversioned=0)
    monkeypatch.setattr(coverage, "load_runs", lambda ctx, statuses: view)
    ctx = SimpleNamespace(system={"number": 2},
                          data=SimpleNamespace(tools=SimpleNamespace(tool_for=lambda t: Raising())))
    with caplog.at_level(logging.ERROR, logger="report_renderer.coverage"):
        out = coverage.coverage_for(ctx, ["O1"], [{"objective_id": "O1", "tests": ["LangBiTe"]}])
    assert out["O1"].status == "evidence"
    records = [r for r in caplog.records if r.name == "report_renderer.coverage"]
    assert len(records) == 1 and records[0].exc_info is not None
    assert "LangBiTe" in records[0].getMessage() and "ref " in records[0].getMessage()
