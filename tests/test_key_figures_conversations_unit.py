"""Key figures' conversation figure, from stand-in runs handed in directly. No database."""
from types import SimpleNamespace

from report_renderer.blocks.key_figures import KeyFiguresBlock
from report_renderer.conversations import CONVERSATION_METRIC


def _talk(category, orgs):
    return {"name": CONVERSATION_METRIC, "dimensions": {"category": category, "scenario": "P1", "register": "basic",
                                                          "language": "en", "repetition": 1, "organisations": orgs}}


def _run(person_orgs):
    run = SimpleNamespace(measurements=[_talk("BASELINE", "A"), _talk("AGE", person_orgs)],
                          target={"label": "OpenAI"})
    return SimpleNamespace(run=run, tool={"display_name": "LangBiTe"})


def _ctx():
    return SimpleNamespace(t=lambda text, **kw: text.format(**kw), percent_format="{value}%", decimal_separator=".",
                           percent=lambda share: f"{share * 100:g}%")


def _figure(runs):
    out = {"tools": []}
    KeyFiguresBlock._conversation_figures(SimpleNamespace(evaluations=[SimpleNamespace(runs=runs)]), _ctx(), out)
    return out["tools"][0]


def test_the_treated_like_the_baseline_figure_says_how_many_runs_it_pools():
    assert _figure([_run("A"), _run("B")])["note"] == "over 2 runs"
    assert _figure([_run("A")])["note"] == "over 1 run"
