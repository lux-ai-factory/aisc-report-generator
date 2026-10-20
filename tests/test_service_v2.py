"""The renderer service and registry: routes, packaging, tool renderer contract versions, and the labels
and help texts of block options.
"""
import logging
import textwrap
import tomllib
from pathlib import Path

import pytest

from conftest import IDS, need
from report_renderer.blocks import BUILTIN_BLOCKS
from v2_core_helpers import H, service

ROOT = Path(__file__).resolve().parents[1]
NEW_BUILTINS = ["chapter", "appendix", "chart", "key_figures", "changes_since"]


def block_types(deps):
    r = service(deps).get("/v1/block-types", headers=H)
    assert r.status_code == 200
    return {t["type_id"]: t for t in r.json()}


# Routes.

@pytest.mark.db
@pytest.mark.parametrize("method,path,body", [
    ("get", "/v1/languages", None),
    ("post", "/v1/coverage-choices", {"project_id": IDS["A"], "system_id": IDS["A_V2"]}),
])
def test_routes_no_caller_used_are_gone(deps, method, path, body):
    """The composer never called these; /health still lists the languages."""
    client = service(deps)
    kw = {"json": body} if body is not None else {}
    assert getattr(client, method)(path, **kw).status_code == 401
    assert getattr(client, method)(path, headers=H, **kw).status_code == 404


@pytest.mark.db
def test_health_gains_interface_version_and_languages(deps):
    body = service(deps).get("/health", headers=H).json()
    assert body.get("interface_version") == 2
    # the health answer lists English only
    assert [x if isinstance(x, str) else x.get("code") for x in body.get("languages", [])] == ["en"]


@pytest.mark.db
def test_block_types_gain_description_and_new_instance_options(deps):
    for t in block_types(deps).values():
        assert "description" in t and isinstance(t["description"], str), t["type_id"]
        assert "new_instance_options" in t and isinstance(t["new_instance_options"], dict), t["type_id"]


@pytest.mark.db
def test_dashboard_chart_points_to_the_chart_block(deps):
    assert block_types(deps)["dashboard_chart"]["description"] == (
        "Shows a results dashboard chart's comments and data. For a chart drawn in the report, use the Chart section.")


# Tool renderer packages: optional, found when installed.

@pytest.mark.db
def test_health_lists_the_three_tool_renderers(deps):
    for m in ("aisc_report_plugin_langbite", "aisc_report_plugin_strongreject", "aisc_report_plugin_promptfoo"):
        pytest.importorskip(m, reason="optional tool renderer, not installed")
    names = service(deps).get("/health", headers=H).json()["tool_renderers"]
    for tool in ("LangBiTe", "StrongREJECT", "Promptfoo"):
        assert tool in names, f"missing feature: tool renderer for {tool}"


def test_new_dependencies():
    """python-docx and cairosvg are runtime dependencies (the tool packages are optional, see
    test_standalone_packaging.py)."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = " ".join(project["project"]["dependencies"])
    for name in ("python-docx", "cairosvg"):
        assert name in deps, f"missing runtime dependency {name}"


# Tool renderer contract versions.

TOOLS_V = textwrap.dedent('''
    from aisc_report_plugin_interface import BaseToolRenderer

    class OldToolRenderer(BaseToolRenderer):
        tool_names = ("OldTool",)
        def render(self, run, ctx):
            return "old"

    class NewToolRenderer(BaseToolRenderer):
        tool_names = ("NewTool",)
        contract_version = 2
        def render(self, run, ctx):
            return "new"

    class FutureToolRenderer(BaseToolRenderer):
        tool_names = ("FutureTool",)
        contract_version = 3
        def render(self, run, ctx):
            return "future"
''')


def test_contract_1_and_2_load_a_higher_one_is_skipped(tmp_path, caplog):
    (tmp_path / "tools_v.py").write_text(TOOLS_V)
    caplog.set_level(logging.WARNING)
    reg = need("report_renderer.registry", "build_registry")(entry_points=[], plugin_dirs=[tmp_path])
    names = reg.tool_names()
    assert "OldTool" in names and "NewTool" in names
    assert "FutureTool" not in names
    assert any("needs a newer report renderer" in r.getMessage() for r in caplog.records)


def test_built_in_contract_versions():
    reg = need("report_renderer.registry", "build_registry")(entry_points=[])
    expected = {"control_objectives": 2, "test_results": 2, "free_text": 2, "summary_coverage": 2,
                "cover": 1, "ai_card": 1, "risk_classification": 1, "control_answers": 1, "dashboard_chart": 1,
                **{t: 1 for t in NEW_BUILTINS}}
    got = {t: getattr(reg.block(t), "contract_version", None) for t in expected}
    assert got == expected


# Two renderers of one tool refuse to start.

DUP = textwrap.dedent('''
    from aisc_report_plugin_interface import BaseToolRenderer

    class FirstLangbite(BaseToolRenderer):
        tool_names = ("LangBiTe-dup",)
        contract_version = 2
        def render(self, run, ctx):
            return "a"

    class SecondLangbite(BaseToolRenderer):
        tool_names = ("langbite dup",)
        contract_version = 2
        def render(self, run, ctx):
            return "b"
''')


def test_two_contract_2_renderers_of_one_tool_refuse_to_start(tmp_path):
    """Contract 2 renderers are refused like any others when two claim one tool."""
    (tmp_path / "dup.py").write_text(DUP)
    Duplicate = need("report_renderer.registry", "DuplicateToolRenderer")
    with pytest.raises(Duplicate):
        need("report_renderer.registry", "build_registry")(entry_points=[], plugin_dirs=[tmp_path])


# Labels, help texts and "More options".

# Read from the code, not copied: a copied list once left out test_runs, so its labels went untested.
BUILTINS = [cls.type_id for cls in BUILTIN_BLOCKS]

MORE = {
    "cover": {"show_logo", "show_generated_by"},
    "ai_card": {"show_graph_stats"},
    "risk_classification": {"show_impact_areas"},
    "control_objectives": {"show_rationale", "show_quotes", "objectives", "include_unrated", "show_severity"},
    "test_results": {"statuses", "show_measurements", "show_artifacts", "show_charts"},
    "control_answers": {"include_archived"},
    "dashboard_chart": {"include_replies", "width", "height"},
    "summary_coverage": {"links"},
    "free_text": {"format"},
    "chart": {"runs", "show_table", "max_bars", "orientation"},
    "key_figures": {"show_tool_headlines"},
    "changes_since": {"show_unchanged"},
    "chapter": {"page_break_before"},
    "appendix": {"title"},
    "test_runs": set(),
}
MAIN = {
    "cover": {"report_title", "subtitle"},
    "ai_card": {"show_components", "show_tags"},
    "risk_classification": {"stated_risk_class", "show_chains"},
    "control_objectives": {"group_by", "requirements", "min_severity", "show_status"},
    "test_results": {"tools", "targets", "metrics", "detail"},
    "control_answers": {"checklists", "show_unanswered", "show_scores"},
    "dashboard_chart": {"chart_id", "show_comments"},
    "summary_coverage": {"show_uncovered_only", "requirements"},
    "free_text": {"text"},
    "chart": {"dataset", "tool_chart", "metric", "dimension"},
    "key_figures": {"figures"},
    "changes_since": {"compare_to", "sections"},
    "chapter": {"title", "intro"},
    "appendix": set(),
    "test_runs": {"detail"},
}
COMMON_MORE = {"title", "page_break_before", "commentary_position"}


def _enum_values(prop):
    values = list(prop.get("enum", []))
    for key in ("items", ):
        if isinstance(prop.get(key), dict):
            values += prop[key].get("enum", [])
    return values


@pytest.mark.db
@pytest.mark.parametrize("type_id", BUILTINS)
def test_every_property_has_a_title_a_description_and_enum_labels(deps, type_id):
    types = block_types(deps)
    assert type_id in types, f"missing feature: block type {type_id}"
    props = types[type_id]["options_schema"]["properties"]
    for name, prop in props.items():
        assert (prop.get("title") or "").strip(), f"{type_id}.{name} has no title"
        assert (prop.get("description") or "").strip(), f"{type_id}.{name} has no description"
        values = _enum_values(prop)
        if values:
            labels = prop.get("x-aisc-enum-labels", {})
            assert all(str(v) in labels and labels[str(v)] for v in values), f"{type_id}.{name} enum labels"


@pytest.mark.db
@pytest.mark.parametrize("type_id", BUILTINS)
def test_main_and_more_options_split(deps, type_id):
    types = block_types(deps)
    assert type_id in types, f"missing feature: block type {type_id}"
    props = types[type_id]["options_schema"]["properties"]
    more = {n for n, p in props.items() if p.get("x-aisc-more") is True}
    main = set(props) - more - {"commentary"}
    expected_more = MORE[type_id] | (COMMON_MORE - MAIN[type_id])
    assert more == expected_more
    assert main == MAIN[type_id]
    assert len(main) <= 4
    assert props.get("commentary", {}).get("x-aisc-more") is not True
