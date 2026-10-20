"""The words the composer shows for the blocks' options: tests and runs, the system and its components,
the results dashboard. No database."""
from report_renderer.blocks.chart import ChartBlock
from report_renderer.blocks.dashboard_chart import DashboardChartBlock
from report_renderer.blocks.key_figures import KeyFiguresBlock
from report_renderer.blocks.test_results import TestResultsBlock
from report_renderer.blocks.test_runs import TestRunsBlock


def _props(cls):
    return cls.options_schema["properties"]


def test_the_test_blocks_speak_of_tests_not_tools():
    assert TestResultsBlock.description == "The tests' results for this version, one section per evaluation."
    assert TestRunsBlock.description == "The test runs in the report's period: when they ran, the tests and their configuration."
    detail = _props(TestRunsBlock)["detail"]
    assert detail["description"] == "One line per run, or each test with its start, end and configuration."
    assert detail["x-aisc-enum-labels"]["full"] == "Each test"
    results = _props(TestResultsBlock)
    assert results["detail"]["description"] == "Full results, or only each test's summary and chart."
    assert results["show_measurements"]["description"] == "Shows the measurements of tests without a dedicated renderer."
    assert results["show_charts"]["description"] == "Lets each test draw its charts in its section."
    assert _props(ChartBlock)["tool_chart"]["title"] == "Test chart"
    assert _props(ChartBlock)["tool_chart"]["description"] == "Which chart of which test."
    headlines = _props(KeyFiguresBlock)["show_tool_headlines"]
    assert headlines["title"] == "Show test headlines"
    assert headlines["description"] == "Adds the main numbers of each test with a dedicated renderer."


def test_the_dashboard_chart_does_not_name_the_product():
    assert "Superset" not in DashboardChartBlock.description
    assert DashboardChartBlock.description.startswith("Shows a results dashboard chart's comments and data.")


def test_the_checklist_and_dashboard_blocks_are_named_for_what_they_hold():
    from report_renderer.blocks.changes_since import SECTION_LABELS
    from report_renderer.blocks.control_answers import ControlAnswersBlock
    assert ControlAnswersBlock.title == "Checklist answers"
    assert SECTION_LABELS["controls"] == "Checklist answers"
    assert DashboardChartBlock.title == "Results dashboard chart"
    assert DashboardChartBlock.description.endswith("use the Chart section.")
