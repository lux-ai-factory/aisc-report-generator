"""Key figures, checklist answers and result files say what is true, drawn from stand-ins handed in directly.
No database: the readers the block calls are stand-ins, and the templates are rendered with plain Jinja."""
import re
from pathlib import Path
from types import SimpleNamespace

import jinja2

from report_renderer.blocks import key_figures
from report_renderer.blocks.key_figures import KeyFiguresBlock
from report_renderer.coverage import STATUSES

TEMPLATES = Path(key_figures.__file__).resolve().parent / "templates"


def _t(text, **kw):
    return text.format(**kw)


def _render(name, **values):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES)), autoescape=True)
    return env.get_template(name).render(t=_t, number=str, **values)


def _card_with_risks_and_no_assessment():
    risks = [{"id": f"risk{n}", "name": f"Risk {n}"} for n in range(5)]
    co = SimpleNamespace(assessment=lambda: None, mappings=lambda: [], objective_ids=lambda: [],
                         newest_newer_assessment=lambda: None)
    q = SimpleNamespace(card=lambda: {"id": "card"}, risks=lambda: risks, newest_newer_card=lambda: None)
    return SimpleNamespace(t=_t, system={"number": 1}, data=SimpleNamespace(control_objectives=co, qualification=q))


def test_the_risks_figure_counts_the_cards_risks_before_control_objectives_are_done():
    ctx = _card_with_risks_and_no_assessment()
    figure = KeyFiguresBlock()._risks(ctx, {}, {"newest": []})
    assert "na" not in figure, f"the card holds 5 risks but the figure is not available: {figure}"
    assert figure.get("value") == "5", figure


def test_the_risks_figure_never_says_there_are_no_control_objectives_when_the_card_has_risks():
    ctx = _card_with_risks_and_no_assessment()
    figure = KeyFiguresBlock()._risks(ctx, {}, {"newest": []})
    assert "No control objectives" not in str(figure), figure


def test_the_coverage_note_keeps_each_status_apart_from_its_neighbours(monkeypatch):
    ids = [f"O{n}" for n in range(7)]
    monkeypatch.setattr(key_figures, "coverage_for",
                        lambda ctx, oids, links: {oid: SimpleNamespace(status="not covered") for oid in oids})
    ctx = SimpleNamespace(t=_t, system={"number": 1}, report=SimpleNamespace(coverage_links={}))
    out = {"co": {"rows": [], "ids": ids}, "newest": []}
    note = KeyFiguresBlock()._coverage(ctx, {}, out)["note"]
    separator = re.match(r".*?: \d+(\W+)", note).group(1)
    parts = note.split(separator)
    unreadable = [p for p in parts if not re.fullmatch(r"[^:]+: \d+", p)]
    assert not unreadable, f"parts without a count, as a reader splits the note: {unreadable} in {note!r}"
    assert len(parts) == len(STATUSES) - 1, note


def test_a_checklist_submission_number_is_not_worded_as_a_version():
    ca = SimpleNamespace(checklist={"id": "cl-1", "title": "Transparency", "source_name": "", "control_topic": "T"},
                         submission={"label": "report version", "status": "Closed", "version": 2,
                                     "questions_version": None},
                         mean=None, answered=0, total=0)
    html = _render("control_answers.html.j2", lists=[{"c": ca, "rows": []}], show_scores=False, hidden=0)
    assert "version 2" not in html, f"the submission number reads as a card version: {html.strip()[:400]!r}"
    assert "submission 2" in html, html.strip()[:400]


def test_a_result_file_of_unknown_size_never_reads_none_bytes():
    run = {"tool": "LangBiTe", "target": "", "components": "", "status": "Done", "no_metrics": False,
           "section": "", "artifacts": [{"name": "results.csv", "file_size": None}]}
    ev = {"name": "Run 3", "status": "Done", "date": "2026-11-13", "short": "abc", "runs": [run], "unmatched": ""}
    html = _render("test_results.html.j2", evaluations=[ev])
    assert "results.csv" in html
    assert "None bytes" not in html, f"an unknown size is printed as None: {html[html.find('results.csv') - 5:][:60]!r}"


def test_a_result_file_of_known_size_says_its_size():
    run = {"tool": "LangBiTe", "target": "", "components": "", "status": "Done", "no_metrics": False,
           "section": "", "artifacts": [{"name": "results.csv", "file_size": 2048}]}
    ev = {"name": "Run 3", "status": "Done", "date": "2026-11-13", "short": "abc", "runs": [run], "unmatched": ""}
    assert "2048 bytes" in _render("test_results.html.j2", evaluations=[ev])
