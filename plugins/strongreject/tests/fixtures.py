"""StrongREJECT runs as the renderer hands them over.

Names and descriptions are exactly what aisc-plugin-strongreject 0.1.0 writes:
~/aisc-install/def_plugins/aisc-plugin-strongreject/src/aisc_plugin_strongreject/plugin.py
  line 365-368 "StrongREJECT Harmfulness": success "Mean harmfulness across all jailbreaks (0-1, lower is
               safer).", failure 0.0 with the error or "No score produced"
  line 374-376 "Jailbreak Resistance": "1 - harmfulness. Share the model held the line (higher is safer).",
               failure 0.0 "Not measured"
  line 382-385 "Worst-Case Jailbreak Harmfulness": "Most effective jailbreak: {key} (lower is safer).",
               failure 0.0 "No attacked jailbreaks"
  line 391-394 "Baseline Harmfulness (no jailbreak)": "Harmfulness with no jailbreak applied — the model's
               plain refusal behaviour.", failure 0.0 "No 'none' baseline run"
  line 401-403 "Harmfulness | {jailbreak}": "Mean StrongREJECT score over {n} prompts (lower is safer)."
The values are those of plugin runs 722 (scored) and 711 (no scores) in seed_tools.sql.
"""
from conftest import I, need

TOOL = {"display_name": "StrongREJECT", "name": "StrongRejectPlugin", "package_name": "aisc-plugin-strongreject",
        "version": "0.1.0"}
LANGBITE = {"display_name": "LangBiTe", "name": "LangBiteEvaluationPlugin", "package_name": "aisc-plugin-langbite"}

OK_HARM = "Mean harmfulness across all jailbreaks (0-1, lower is safer)."
OK_RES = "1 - harmfulness. Share the model held the line (higher is safer)."
OK_BASE = "Harmfulness with no jailbreak applied — the model's plain refusal behaviour."


def m(name, score, description):
    return {"observation_id": 7202, "name": name, "metric": name, "score": score, "unit": None, "uncertainty": 0.0,
            "dimensions": None, "direction": None, "description": description, "error": None}


def jb(key, score, n=20):
    return m(f"Harmfulness | {key}", score, f"Mean StrongREJECT score over {n} prompts (lower is safer).")


SCORED = [
    m("StrongREJECT Harmfulness", 0.2, OK_HARM),
    m("Jailbreak Resistance", 0.8, OK_RES),
    m("Worst-Case Jailbreak Harmfulness", 0.45, "Most effective jailbreak: pair (lower is safer)."),
    m("Baseline Harmfulness (no jailbreak)", 0.05, OK_BASE),
    # Out of order on purpose: none first, then by name
    jb("pair", 0.45), jb("none", 0.05), jb("aim", 0.1), jb("base64", 0.2),
]
NOT_SCORED = [
    m("StrongREJECT Harmfulness", 0.0, "No score produced"),
    m("Jailbreak Resistance", 0.0, "Not measured"),
    m("Worst-Case Jailbreak Harmfulness", 0.0, "No attacked jailbreaks"),
    m("Baseline Harmfulness (no jailbreak)", 0.0, "No 'none' baseline run"),
]


def run(measurements=None, artifacts=None, pid="f2ea0000-0000-4000-8000-000000000722"):
    ToolRun = need(I, "ToolRun")
    return ToolRun(
        evaluation={"pid": "f2e00000-0000-4000-8000-000000000072", "status": "Done",
                    "created_at": "2026-09-19T09:00:00+00:00", "name": "Evaluation 2: LangBiTe, StrongREJECT",
                    "number": 2},
        evaluation_plugin={"pid": pid, "name": "StrongRejectPlugin", "status": "Done", "error_message": ""},
        tool=TOOL, components=[], observations=[],
        measurements=SCORED if measurements is None else measurements,
        artifacts=artifacts if artifacts is not None else [{"name": "strongreject_per_prompt.csv", "file_size": 4096}])


def failed_run():
    return run(NOT_SCORED, artifacts=[], pid="f2ea0000-0000-4000-8000-000000000711")
