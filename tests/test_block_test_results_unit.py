"""One run of the Test results block, drawn from stand-ins handed in directly. No database."""
from types import SimpleNamespace

from report_renderer.blocks.test_results import TestResultsBlock
from report_renderer.conversations import CONVERSATION_METRIC


class _Failing:
    def render(self, run, ctx):
        raise RuntimeError("renderer broke")


def _conversation(n):
    return {"name": CONVERSATION_METRIC, "metric": CONVERSATION_METRIC, "score": 1.0,
            "dimensions": {"category": "AGE", "slot": n}}


def test_a_failed_tool_renderer_falls_back_to_a_table_without_the_conversation_rows():
    other = {"name": "Overall Pass Rate", "metric": "Overall Pass Rate", "score": 0.5}
    run = SimpleNamespace(measurements=[_conversation(0), _conversation(1), other], target=None)
    rv = SimpleNamespace(tool={"name": "langbite"}, run=run, components=[], status="done", artifacts=[])
    ctx = SimpleNamespace(t=lambda text, **kw: text.format(**kw), number=str, report=None,
                          data=SimpleNamespace(tools=SimpleNamespace(tool_for=lambda tool: _Failing())))
    options = {"show_charts": False, "show_measurements": True, "show_artifacts": False}
    notices = []
    entry = TestResultsBlock()._run_entry(rv, options, ctx, None, notices, False)
    assert "Overall Pass Rate" in str(entry["section"])
    assert CONVERSATION_METRIC not in str(entry["section"])
    assert any("2 conversation results from 1 run are not listed." in n for n in notices)
