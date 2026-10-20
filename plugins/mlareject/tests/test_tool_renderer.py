"""MLAREJECTToolRenderer: the MLA-Reject section of Test results. It computes from `run.measurements`
and needs no database session."""
from conftest import need

P = "aisc_report_plugin_mlareject"
I = "aisc_report_plugin_interface"

MLA = {"display_name": "MLA-Reject", "name": "MLARejectEvaluationPlugin", "package_name": "aisc-plugin-mlareject"}
LANGBITE = {"display_name": "LangBiTe", "name": "LangBiTeEvaluationPlugin", "package_name": "aisc-plugin-langbite"}


def run():
    ToolRun = need(I, "ToolRun")
    ms = [
        {"name": "score", "metric": "score", "score": 4.0, "unit": None, "uncertainty": 0.0,
         "dimensions": {"language": "en", "jailbreak": "dan", "category": "<script>alert(1)</script>",
                        "response": "HARMFUL RESPONSE TEXT"}},
        {"name": "score", "metric": "score", "score": 1.0, "unit": None, "uncertainty": 0.0,
         "dimensions": {"language": "fr", "jailbreak": "aim", "category": "violence"}},
    ]
    return ToolRun(evaluation={"pid": "e1", "status": "Done"},
                   evaluation_plugin={"pid": "ep1", "name": "MLARejectEvaluationPlugin", "status": "Done"},
                   tool={**MLA, "version": "1.0"}, components=[], observations=[], measurements=ms, artifacts=[])


def renderer():
    return need(P, "MLAREJECTToolRenderer")()


def test_the_tool_renderer_is_a_base_tool_renderer():
    Base = need(I, "BaseToolRenderer")
    assert isinstance(renderer(), Base)


def test_it_claims_mla_reject_and_nothing_else():
    cls = need(P, "MLAREJECTToolRenderer")
    assert cls.matches(MLA)
    assert not cls.matches(LANGBITE)


def test_it_renders_the_statistics_from_the_run():
    html = renderer().render(run(), ctx=None)
    assert "Mean score" in html
    assert "2.500" in html            # (4.0 + 1.0) / 2
    assert "en, fr" in html           # languages
    assert "aim, dan" in html         # jailbreak methods


# Harmful-case texts are omitted
def test_it_never_prints_prompts_or_responses():
    html = renderer().render(run(), ctx=None)
    assert "HARMFUL RESPONSE TEXT" not in html


def test_values_are_escaped():
    html = renderer().render(run(), ctx=None)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# No session, no shared templates of the generator needed
def test_it_renders_without_a_session_or_the_generator():
    import sys

    html = renderer().render(run(), ctx=None)
    assert html.strip()
    assert "resources" not in sys.modules and "resources.sql_alchemy" not in sys.modules
