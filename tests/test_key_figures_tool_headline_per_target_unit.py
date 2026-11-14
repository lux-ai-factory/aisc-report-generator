"""Key figures' test headlines when one tool ran against several back-ends: a headline never passes one back-end's
score off as the tool's, it names the back-end (the run's target) and the run it comes from. Stand-in runs handed
in directly, no database."""
from types import SimpleNamespace

import pytest

from report_renderer.blocks import key_figures
from report_renderer.blocks.key_figures import KeyFiguresBlock

TOOL = {"name": "StrongREJECT (Mijke)", "display_name": "StrongREJECT (Mijke)"}
# three Done runs of the same tool, oldest first, each against another back-end
RUNS = [
    (25, "Mijke jailbreaks, OpenAI", "OpenAI gpt-4o", "0.712"),
    (61, "Mijke jailbreaks, local", "Local model", "0.10"),
    (77, "Mijke jailbreaks, Mistral", "Mistral large", "0.594"),
]


class Renderer:
    contract_version = 2


def _run_view(run_id, run_name, target, score):
    run = SimpleNamespace(evaluation={"id": run_id}, evaluation_plugin={"id": run_id, "name": run_name},
                          tool=TOOL, measurements=[], target={"label": target, "kind": "system"}, score=score)
    return SimpleNamespace(tool=TOOL, run=run, components=[], status="Done", artifacts=[])


@pytest.fixture
def tiles(monkeypatch):
    view = SimpleNamespace(evaluations=[SimpleNamespace(runs=[_run_view(*r)], evaluation={"id": r[0]})
                                        for r in RUNS], unversioned=0)
    monkeypatch.setattr(key_figures, "load_runs", lambda ctx, statuses=None: view)
    monkeypatch.setattr(key_figures, "headline_items",
                        lambda renderer, run, ctx: [{"label": "Jailbreak resistance", "value": run.score}])
    ctx = SimpleNamespace(
        t=lambda text, **kw: text.format(**kw),
        system={"number": 1},
        data=SimpleNamespace(engine=SimpleNamespace(newest_newer_evaluation=lambda: None),
                             tools=SimpleNamespace(tool_for=lambda tool: Renderer())),
        translate_for=lambda package: (lambda text: text),
        percent=lambda share: f"{share * 100:g}%",
    )
    out = {"tools": [], "newest": []}
    KeyFiguresBlock()._tests(ctx, {"show_tool_headlines": True}, out)
    jailbreak = [t for t in out["tools"] if "Jailbreak resistance" in t["label"]]
    assert jailbreak, f"no jailbreak headline at all: {out['tools']}"
    return jailbreak


def _text(tile):
    return " ".join(str(tile.get(k, "")) for k in ("label", "value", "note"))


def test_each_jailbreak_headline_names_the_back_end_it_was_measured_on(tiles):
    for tile in tiles:
        named = [target for _id, _name, target, _score in RUNS if target in _text(tile)]
        assert named, f"the headline names no back-end: {tile}"


def test_each_jailbreak_headline_names_the_run_it_comes_from(tiles):
    for tile in tiles:
        named = [run_id for run_id, name, _t, _s in RUNS if name in _text(tile) or f"run {run_id}" in _text(tile)]
        assert named, f"the headline names no run: {tile}"


def test_every_back_end_gets_its_own_jailbreak_headline(tiles):
    shown = {target: score for _id, _name, target, score in RUNS
             for tile in tiles if target in _text(tile) and score in _text(tile)}
    assert shown == {target: score for _id, _name, target, score in RUNS}, [_text(t) for t in tiles]
