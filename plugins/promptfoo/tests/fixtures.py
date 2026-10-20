"""promptfoo runs as the renderer hands them over.

Names, units and descriptions are exactly what aisc-plugin-promptfoo 0.1.0 writes:
~/aisc-virgin/plugins/aisc-plugin-promptfoo/src/aisc_plugin_promptfoo/plugin.py
  line 1081-1082 pass_rate "rate (higher is better)"; 1089-1090 fail_rate "rate (lower is better)";
  line 1097-1098 refusal_rate "rate" (the first three are absent when promptfoo reports no success data);
  line 1102-1104 mean_latency_ms "ms (lower is better)"; 1108-1110 total_cost "USD (lower is better)";
  line 1114-1116 n_tests "count". A failed run writes no measurement at all.
The values are those of plugin runs 741 (all six), 731 (latency, cost, tests) and 751 (none) in seed_tools.sql.
"""
from conftest import I, need

TOOL = {"display_name": "Promptfoo", "name": "PromptfooPlugin", "package_name": "aisc-plugin-promptfoo",
        "version": "0.1.0"}
LANGBITE = {"display_name": "LangBiTe", "name": "LangBiteEvaluationPlugin", "package_name": "aisc-plugin-langbite"}


def m(name, score, unit, description):
    return {"observation_id": 7401, "name": name, "metric": name, "score": score, "unit": unit, "uncertainty": 0.0,
            "dimensions": None, "direction": None, "description": description, "error": None}


LATENCY_COST_TESTS = [
    m("mean_latency_ms", 640.0, "ms (lower is better)", "Average model response time across all tests."),
    m("total_cost", 0.0, "USD (lower is better)", "Total API cost across all tests."),
    m("n_tests", 12.0, "count", "Number of test cases run."),
]
FULL = [
    m("pass_rate", 0.85, "rate (higher is better)", "Share of tests that passed all of their assertions."),
    m("fail_rate", 0.15, "rate (lower is better)", "Share of tests that failed at least one assertion."),
    m("refusal_rate", 0.1, "rate", "Share of tests where the model refused to answer."),
    m("mean_latency_ms", 812.4, "ms (lower is better)", "Average model response time across all tests."),
    m("total_cost", 0.01234, "USD (lower is better)", "Total API cost across all tests."),
    m("n_tests", 40.0, "count", "Number of test cases run."),
]


def run(measurements=None, status="Done", artifacts=None, number=4):
    ToolRun = need(I, "ToolRun")
    return ToolRun(
        evaluation={"pid": f"f2e00000-0000-4000-8000-00000000007{number + 1}", "status": status,
                    "created_at": "2026-09-19T11:00:00+00:00", "name": f"Evaluation {number}: Promptfoo",
                    "number": number},
        evaluation_plugin={"pid": "f2ea0000-0000-4000-8000-000000000741", "name": "PromptfooPlugin",
                           "status": status, "error_message": "promptfoo exited with code 1" if status == "Failed" else ""},
        tool=TOOL, components=[], observations=[],
        measurements=FULL if measurements is None else measurements,
        artifacts=artifacts if artifacts is not None else [{"name": "promptfoo_results.json", "file_size": 8192},
                                                           {"name": "plugin_execution.log", "file_size": 512}])
