"""The Chart block.

Markup contract: each chart is `<figure class="chart" data-kind="bar|hbar">` holding an inline SVG
(see v2_block_helpers). Seed: Mike v2 (checklists "Example Assistant oversight" mean 3, "Example Assistant transparency" mean 4.5;
Promptfoo n_tests 12 in evaluation 3 and 40 in evaluation 4), Alpha v1 (MLA-Reject 'score' with
dimensions: en 4.0 and 2.5, fr 1.0; category hate 4.0, violence 1.0, one without category).
"""
import pytest

from conftest import IDS, need
from v2_block_helpers import (MIKE_MAP, block_class, charts, need_tool_package, notices_and_text,
                              one, table_rows)

pytestmark = pytest.mark.db
DATASETS = ["coverage_status", "checklist_scores", "tool_chart", "metric_by_evaluation", "metric_by_dimension"]


# Declaration.

def test_declaration_and_defaults(deps):
    cls = block_class(deps, "chart")
    assert cls.title == "Chart"
    assert set(cls.reads) == {"platform", "engine", "controls", "control_objectives"}
    props = cls.full_options_schema()["properties"]
    assert props["dataset"]["enum"] == DATASETS
    for name in ("tool_chart", "metric", "dimension", "runs", "show_table", "max_bars", "orientation"):
        assert name in props, name
    d = cls.full_default_options()
    assert d["dataset"] == "coverage_status" and d["runs"] == "latest" and d["show_table"] is True
    assert d["max_bars"] == 20 and d["orientation"] == "auto"


@pytest.mark.parametrize("bad", [2, 41])
def test_max_bars_range(deps, bad):
    cls = block_class(deps, "chart")
    assert cls.options_problems({**cls.full_default_options(), "max_bars": bad})


# Dependent options are required.

@pytest.mark.parametrize("dataset,needed", [("tool_chart", "tool_chart"), ("metric_by_evaluation", "metric"),
                                            ("metric_by_dimension", "metric"), ("metric_by_dimension", "dimension")])
def test_the_chosen_dataset_requires_its_option(deps, dataset, needed):
    cls = block_class(deps, "chart")
    options = {**cls.full_default_options(), "dataset": dataset}
    for k in ("tool_chart", "metric", "dimension"):
        options.pop(k, None)
    problems = cls.options_problems(options)
    assert {"pointer": f"/{needed}", "message": "is required"} in problems, problems


def test_coverage_status_needs_nothing_else(deps):
    cls = block_class(deps, "chart")
    options = {k: v for k, v in cls.full_default_options().items() if k not in ("tool_chart", "metric", "dimension")}
    assert cls.options_problems(options) == []


# Datasets.

def test_coverage_status_from_the_layout_map(deps):
    t, st, node, _ = one(deps, "chart", dataset="coverage_status", coverage_links=MIKE_MAP)
    assert st["status"] == "ok"
    assert len(charts(node)) == 1 and charts(node)[0].find("svg") is not None
    rows = [r for r in table_rows(node) if len(r) == 2]
    assert rows[-4:] == [["evidence", "2"], ["evidence, attention", "0"], ["no evidence", "1"], ["not covered", "1"]]


def test_checklist_scores(deps):
    _, st, node, _ = one(deps, "chart", dataset="checklist_scores")
    rows = [r for r in table_rows(node) if len(r) == 2]
    labels = [r[0] for r in rows if r[0].startswith("Example Assistant")]
    assert labels == ["Example Assistant oversight", "Example Assistant transparency"]
    values = {r[0]: r[1] for r in rows}
    assert values["Example Assistant oversight"].startswith("3") and values["Example Assistant transparency"].startswith("4.5")


def test_metric_by_evaluation(deps):
    _, st, node, _ = one(deps, "chart", dataset="metric_by_evaluation", metric={"tool": "Promptfoo", "metric": "n_tests"})
    rows = [r for r in table_rows(node) if len(r) == 2 and r[0].startswith("Evaluation")]
    assert rows == [["Evaluation 3", "12"], ["Evaluation 4", "40"]]


def test_metric_by_dimension(deps):
    _, st, node, _ = one(deps, "chart", project="A", system="A_V1", dataset="metric_by_dimension",
                         metric={"tool": "MLA-Reject", "metric": "score"}, dimension="category")
    rows = [r for r in table_rows(node) if len(r) == 2 and r[0] in ("hate", "unknown", "violence")]
    assert [r[0] for r in rows] == ["hate", "unknown", "violence"]
    assert rows[1][1].startswith("2.5")


def test_tool_chart_latest_run(deps):
    need_tool_package("aisc_report_plugin_langbite", "LANGBITEToolRenderer")
    _, st, node, _ = one(deps, "chart", dataset="tool_chart",
                         tool_chart={"tool": "LangBiTe", "chart": "pass_rate_by_concern"})
    assert st["status"] == "ok" and len(charts(node)) == 1
    labels = [r[0] for r in table_rows(node) if len(r) == 2]
    assert {"ageism", "gender", "religion"} <= set(labels)


def test_tool_chart_each_run(deps):
    need_tool_package("aisc_report_plugin_strongreject", "STRONGREJECTToolRenderer")
    t, st, node, _ = one(deps, "chart", dataset="tool_chart", runs="each",
                         tool_chart={"tool": "StrongREJECT", "chart": "harmfulness_by_jailbreak"})
    assert "Evaluation 2: LangBiTe, StrongREJECT" in t


# Nothing to draw, not available.

def test_no_scored_checklist_answers(deps):
    t, st, *_ = one(deps, "chart", project="C", system="C_V1", dataset="checklist_scores")
    assert st["status"] == "empty" and "No scored checklist answers for version 1." in t


def test_coverage_status_without_an_assessment(deps):
    t, st, *_ = one(deps, "chart", project="C", system="C_V1", dataset="coverage_status")
    assert st["status"] == "empty" and "version 1" in t


def test_a_tool_chart_nobody_offers(deps):
    t, st, *_ = one(deps, "chart", project="A", system="A_V2", dataset="tool_chart", allow_error=True,
                    tool_chart={"tool": "Mystery Tool", "chart": "anything"})
    assert "Unknown block type" not in " ".join(st["notices"]), "missing feature: built-in block type chart"
    assert st["status"] == "error" and "This chart is not available on this platform." in t


# Orientation.

def test_auto_orientation(deps):
    _, _, node, _ = one(deps, "chart", dataset="coverage_status", coverage_links=MIKE_MAP)
    assert charts(node)[0]["data-kind"] == "hbar"          # "evidence, attention" is longer than 12
    _, _, node, _ = one(deps, "chart", dataset="metric_by_evaluation", metric={"tool": "Promptfoo", "metric": "n_tests"})
    assert charts(node)[0]["data-kind"] == "bar"           # 2 bars, labels of 12 characters


def test_forced_orientation(deps):
    _, _, node, _ = one(deps, "chart", dataset="coverage_status", coverage_links=MIKE_MAP, orientation="vertical")
    assert charts(node)[0]["data-kind"] == "bar"


# Max bars.

def test_more_bars_than_max(deps):
    t, st, node, _ = one(deps, "chart", dataset="coverage_status", coverage_links=MIKE_MAP, max_bars=3)
    assert "1 more group is not shown." in notices_and_text(t, st)
    rows = [r for r in table_rows(node) if len(r) == 2]
    assert len(rows[-4:]) == 4 and rows[-1][0] == "not covered"     # the table keeps every row


# Table.

def test_table_can_be_hidden(deps):
    _, _, node, _ = one(deps, "chart", dataset="coverage_status", coverage_links=MIKE_MAP, show_table=False)
    assert node.find("table") is None and charts(node)


# Staleness per source.

@pytest.mark.parametrize("system,options,stale", [
    ("A_V2", {"dataset": "checklist_scores"}, True),                   # answers for version 3 exist
    ("A_V1", {"dataset": "coverage_status"}, True),                    # an assessment for version 2 exists
    ("A_V2", {"dataset": "coverage_status"}, False),                   # no assessment of version 3
    ("A_V2", {"dataset": "metric_by_evaluation", "metric": {"tool": "LangBiTe", "metric": "bias_rate"}}, True),
])
def test_stale_as_the_block_reading_the_source(deps, system, options, stale):
    _, st, *_ = one(deps, "chart", project="A", system=system, **options)
    assert (st["status"] == "stale") is stale, st


# Choices.

def test_choices(deps):
    cls = block_class(deps, "chart")
    ctx = need("report_renderer.context", "context_for")(IDS["A"], IDS["A_V1"], deps=deps, mode="preview")
    dims = {c["value"] for c in cls().choices(ctx, "dimension")}
    assert {"language", "jailbreak", "category"} <= dims
    ctx = need("report_renderer.context", "context_for")(IDS["M"], IDS["M_V2"], deps=deps, mode="preview")
    metrics = [c["value"] for c in cls().choices(ctx, "metric")]
    assert {"tool": "Promptfoo", "metric": "n_tests"} in metrics


def test_tool_chart_choices(deps):
    need_tool_package("aisc_report_plugin_langbite", "LANGBITEToolRenderer")
    cls = block_class(deps, "chart")
    ctx = need("report_renderer.context", "context_for")(IDS["M"], IDS["M_V2"], deps=deps, mode="preview")
    labels = {c["label"]: c["value"] for c in cls().choices(ctx, "tool_chart")}
    assert labels["LangBiTe: Pass rate by concern"] == {"tool": "LangBiTe", "chart": "pass_rate_by_concern"}
    assert "StrongREJECT: Harmfulness by jailbreak" in labels
