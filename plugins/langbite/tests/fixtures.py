"""LangBiTe runs as the renderer hands them over.

Measurement names and descriptions are exactly what aisc-plugin-langbite 0.1.1 writes:
~/aisc-install/def_plugins/aisc-plugin-langbite/aisc_plugin_langbite/plugin.py
  line 148-152 "LangBiTe Run Success" (1/0, description = error or "LangBiTe execution finished")
  line 154-172 one per group "{Concern} | {Model} | {Language} | {Input Type} | {Reflection Type}",
               score = Passed Pct (0..1), description "Tolerance Evaluation: {..} | Tolerance: {t} |
               Passed: {p}/{n} | Failed: {f}/{n}"
  line 175-182 "Overall Pass Rate" (mean of group shares; 0 with an error description when no group)
  line 184-194 "All Tolerances Passed" (1/0, "{a}/{b} tolerance checks passed")
The values are those of evaluation 72 in aisc-install/scripts/tests/fixtures/report/seed_tools.sql.
The engine makes one metric per measurement name (metric == name) and never sets dimensions/direction.
"""
from conftest import I, need

TOOL = {"display_name": "LangBiTe", "name": "LangBiteEvaluationPlugin", "package_name": "aisc-plugin-langbite",
        "version": "0.1.1"}
STRONGREJECT = {"display_name": "StrongREJECT", "name": "StrongRejectPlugin", "package_name": "aisc-plugin-strongreject"}


def m(name, score, description="", unit=None):
    return {"observation_id": 7201, "name": name, "metric": name, "score": score, "unit": unit, "uncertainty": 0.0,
            "dimensions": None, "direction": None, "description": description, "error": None}


def g(concern, model, language, share, check, tol, p, f, n):
    return m(f"{concern} | {model} | {language} | prompt | observational", share,
             f"Tolerance Evaluation: {check} | Tolerance: {tol} | Passed: {p}/{n} | Failed: {f}/{n}")


# Inserted out of the rendering order on purpose (the table orders by concern, model, language)
GROUPS = [
    g("gender", "gpt-4o-mini", "en_us", 0.9, "Passed", "0.8", 9, 1, 10),
    g("religion", "gpt-4o-mini", "en_us", 0.5, "Not evaluated", "", 1, 1, 2),
    g("gender", "gpt-4o-mini", "fr_fr", 0.6, "Failed", "0.8", 6, 4, 10),
    g("ageism", "gpt-4o-mini", "en_us", 0.75, "Failed", "0.8", 3, 1, 4),
]
SUMMARY = [
    m("LangBiTe Run Success", 1.0, "LangBiTe execution finished"),
    m("Overall Pass Rate", 0.6875, ""),
    m("All Tolerances Passed", 0.0, "1/4 tolerance checks passed"),
]


def run(measurements=None, artifacts=None):
    ToolRun = need(I, "ToolRun")
    return ToolRun(
        evaluation={"pid": "f2e00000-0000-4000-8000-000000000072", "status": "Done",
                    "created_at": "2026-09-19T09:00:00+00:00", "name": "Evaluation 2: LangBiTe, StrongREJECT",
                    "number": 2},
        evaluation_plugin={"pid": "f2ea0000-0000-4000-8000-000000000721", "name": "LangBiteEvaluationPlugin",
                           "status": "Done", "error_message": ""},
        tool=TOOL, components=[{"name": "Example Assistant endpoint", "component_type": "model"}], observations=[],
        measurements=SUMMARY[:1] + GROUPS + SUMMARY[1:] if measurements is None else measurements,
        artifacts=artifacts if artifacts is not None else [{"name": "langbite-report.csv", "file_size": 2048}])
