"""What a layout can ask for: risk identification without operators or an AI Act class, the objectives table with
objective and label together and room for the description. And a figure for a test with conversations."""
import pytest

from conftest import render_one
from test_results_by_test import AGE, MIJKE, conversations, view_of

pytestmark = pytest.mark.db


def test_the_risk_section_can_be_named_risk_identification(deps):
    _, _, node, _ = render_one(deps, "risk_classification", title="Risk identification")
    assert "Risk identification" in node.get_text() and "Risk classification" not in node.get_text()


def test_operators_and_the_ai_act_class_can_be_left_out(deps):
    text, *_ = render_one(deps, "risk_classification", show_classification=False)
    assert "Operators" not in text and "AI Act risk class" not in text


def test_they_are_there_unless_left_out(deps):
    text, *_ = render_one(deps, "risk_classification")
    assert "Operators" in text and "AI Act risk class" in text


def test_the_objectives_table_can_hold_objective_and_label_in_one_column(deps):
    _, _, node, _ = render_one(deps, "summary_coverage", merge_label=True)
    table = node.find("table", class_="coverage")
    assert [th.get_text(strip=True) for th in table.find_all("th")] == ["Objective", "Description", "Tests", "Checklists", "Coverage"]
    first = table.find("tbody").find("tr")
    assert " - " in first.find("td").get_text() and first.find("td").get_text().startswith(first["data-objective"])


def test_merged_the_description_is_twice_as_wide_as_the_others(deps):
    _, _, node, _ = render_one(deps, "summary_coverage", merge_label=True)
    widths = [float(c["style"].split(":")[1].strip(" %;")) for c in node.find("table", class_="coverage").find_all("col")]
    assert len(widths) == 5 and widths[1] == pytest.approx(2 * widths[0], abs=0.1)
    assert widths[0] == widths[2] == widths[3] == widths[4] and sum(widths) == pytest.approx(100, abs=0.5)


def test_a_test_with_conversations_has_its_figure(deps, monkeypatch):
    runs = view_of((MIJKE, "OpenAI", "2026-11-01T10:00:00", conversations("AGE", AGE)),
                   (MIJKE, "Local", "2026-11-01T11:00:00", conversations("AGE", AGE)))
    monkeypatch.setattr("report_renderer.blocks.key_figures.load_runs", lambda *a, **k: runs)
    text, *_ = render_one(deps, "key_figures", figures=["tests"])
    assert "LangBiTe (Mijke): Treated like the baseline" in text
    assert "OpenAI" in text and "Local" in text and "66.7%" in text
