"""Block types and tool renderers the renderer knows, and the options each block type declares."""
import logging
import textwrap
from importlib.metadata import EntryPoint

import pytest

from conftest import need

REG = "report_renderer.registry"
BUILTINS = ["cover", "ai_card", "risk_classification", "control_objectives", "test_results",
            "control_answers", "dashboard_chart", "summary_coverage", "free_text",
            "chapter", "appendix", "chart", "key_figures", "changes_since", "test_runs"]
LANGBITE = {"display_name": "LangBiTe", "name": "LangBiTeEvaluationPlugin", "package_name": "aisc-plugin-langbite"}


def build(**kw):
    return need(REG, "build_registry")(**kw)


def ep(value, group="aisc_report.blocks", name="x"):
    return EntryPoint(name=name, value=value, group=group)


def test_the_nine_blocks_are_built_in():
    reg = build(entry_points=[])
    assert sorted(b.type_id for b in reg.block_types()) == sorted(BUILTINS)


@pytest.mark.parametrize("type_id", BUILTINS)
def test_every_built_in_declares_a_valid_contract(type_id):
    Base = need("aisc_report_plugin_interface", "BaseBlockRenderer")
    cls = build(entry_points=[]).block(type_id)
    assert issubclass(cls, Base)
    cls.validate_declaration()
    assert cls.contract_version >= 1 and cls.title


# options and their defaults
EXPECTED_DEFAULTS = {
    "cover": {"report_title": "AI system assessment report", "subtitle": "", "show_logo": True, "show_generated_by": True},
    "ai_card": {"show_components": True, "show_tags": True, "show_graph_stats": False},
    "risk_classification": {"show_chains": True, "show_impact_areas": True, "stated_risk_class": "not_determined"},
    "control_objectives": {"group_by": "objective", "show_rationale": True, "show_quotes": False, "show_status": True,
                           "requirements": "all", "objectives": "all", "min_severity": None,
                           "include_unrated": True, "show_severity": False},
    "test_results": {"tools": "all", "targets": "all", "statuses": ["Done"], "show_measurements": True, "show_artifacts": False,
                     "metrics": "all", "show_charts": True, "detail": "full"},
    "control_answers": {"checklists": "all", "show_unanswered": True, "show_scores": True, "include_archived": False},
    "dashboard_chart": {"show_comments": True, "include_replies": True, "width": 1200, "height": 700},
    "summary_coverage": {"links": [], "show_uncovered_only": False, "requirements": "all"},
    "free_text": {"format": "plain"},
    "chart": {"dataset": "coverage_status", "runs": "latest", "show_table": True, "max_bars": 20, "orientation": "auto"},
    "key_figures": {"figures": ["version", "risks", "objectives", "coverage", "tests", "checklists"],
                    "show_tool_headlines": True},
    "changes_since": {"compare_to": "previous", "sections": ["card", "objectives", "tests", "controls"],
                      "show_unchanged": False},
    "chapter": {"title": "Chapter", "intro": "", "page_break_before": True},
    "appendix": {},
    "test_runs": {"detail": "summary"},
}


@pytest.mark.parametrize("type_id", BUILTINS)
def test_default_options(type_id):
    """Each built-in block type's default options, including the common options."""
    cls = build(entry_points=[]).block(type_id)
    assert cls.default_options == EXPECTED_DEFAULTS[type_id]
    assert cls.full_default_options() == {"title": "", "page_break_before": False, "commentary": "",
                                          "commentary_position": "after", **EXPECTED_DEFAULTS[type_id]}


def test_chart_id_and_text_are_required_without_default():
    reg = build(entry_points=[])
    assert "chart_id" in reg.block("dashboard_chart").full_options_schema()["required"]
    assert "text" in reg.block("free_text").full_options_schema()["required"]
    text_schema = reg.block("free_text").options_schema["properties"]["text"]
    assert (text_schema["minLength"], text_schema["maxLength"]) == (1, 20000)
    width = reg.block("dashboard_chart").options_schema["properties"]["width"]
    assert (width["minimum"], width["maximum"]) == (400, 1600)


def test_stated_risk_class_values():
    """stated_risk_class is one of not_determined (default), prohibited, high, limited, minimal."""
    prop = build(entry_points=[]).block("risk_classification").options_schema["properties"]["stated_risk_class"]
    assert set(prop["enum"]) == {"not_determined", "prohibited", "high", "limited", "minimal"}


# the composer finds data references by this marker in the schema
@pytest.mark.parametrize("type_id,option", [("control_answers", "checklists"),
                                            ("dashboard_chart", "chart_id"), ("summary_coverage", "links")])
def test_data_references_are_marked_in_the_schema(type_id, option):
    props = build(entry_points=[]).block(type_id).options_schema["properties"]
    assert props[option].get("x-aisc-reference") is True


def test_other_options_are_not_references():
    reg = build(entry_points=[])
    for cls in reg.block_types():
        for name, prop in cls.options_schema.get("properties", {}).items():
            if (cls.type_id, name) not in {("control_answers", "checklists"),
                                           ("dashboard_chart", "chart_id"), ("summary_coverage", "links"),
                                           ("test_results", "metrics"), ("control_objectives", "objectives"),
                                           ("chart", "tool_chart"), ("chart", "metric"),
                                           # target keys are the project's
                                           ("test_results", "targets"),
                                           }:
                assert not prop.get("x-aisc-reference"), (cls.type_id, name)


def test_reads_name_the_data_sources():
    reg = build(entry_points=[])
    assert set(reg.block("free_text").reads) == set()
    assert "engine" in reg.block("test_results").reads
    assert "controls" in reg.block("control_answers").reads
    assert "superset" in reg.block("dashboard_chart").reads
    assert "qualification" in reg.block("ai_card").reads
    for cls in reg.block_types():
        assert "catalogue" not in cls.reads


def test_blocks_from_installed_packages():
    reg = build(entry_points=[ep("plugins_fixture.extra_block:ExtraBlock")])
    assert reg.block("extra_block").__name__ == "ExtraBlock"


def test_a_package_that_fails_to_import_is_skipped(caplog):
    caplog.set_level(logging.WARNING)
    reg = build(entry_points=[ep("no_such_package.blocks:Nothing"), ep("plugins_fixture.extra_block:ExtraBlock")])
    assert reg.block("extra_block")
    assert len(reg.block_types()) == len(BUILTINS) + 1
    assert "no_such_package" in caplog.text


def test_blocks_from_the_plugin_directory(tmp_path):
    (tmp_path / "dir_block.py").write_text(textwrap.dedent('''
        from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult
        class DirBlock(BaseBlockRenderer):
            type_id = "dir_block"; title = "Dir"; contract_version = 1
            options_schema = {"type": "object"}; default_options = {}; reads = ()
            def load(self, ctx, options): return None
            def render(self, data, options, ctx): return BlockResult(html="<p>d</p>", status="ok")
    '''))
    (tmp_path / "broken.py").write_text("raise ImportError('broken plugin')\n")
    reg = build(entry_points=[], plugin_dirs=[tmp_path])
    assert reg.block("dir_block").__name__ == "DirBlock"


def test_a_duplicate_type_id_refuses_to_start(caplog):
    Duplicate = need(REG, "DuplicateBlockType")
    caplog.set_level(logging.ERROR)
    with pytest.raises(Duplicate) as err:
        build(entry_points=[ep("plugins_fixture.extra_block:CoverAgain", name="cover-again")])
    message = str(err.value) + caplog.text
    assert "cover" in message
    assert "plugins_fixture.extra_block" in message       # the plugin's origin
    assert "report_renderer" in message                    # the built-in's origin


def test_register_block_names_both_origins():
    Duplicate = need(REG, "DuplicateBlockType")
    reg = build(builtins=False, entry_points=[])
    extra = need("plugins_fixture.extra_block", "ExtraBlock")
    reg.register_block(extra, origin="first-origin")
    with pytest.raises(Duplicate) as err:
        reg.register_block(extra, origin="second-origin")
    assert "first-origin" in str(err.value) and "second-origin" in str(err.value)


def test_an_unknown_tool_has_no_renderer():
    reg = build(entry_points=[])
    assert reg.tool_for({"display_name": "Nobody", "name": "NobodyPlugin", "package_name": "aisc-plugin-nobody"}) is None


LEGACY = '''
from aisc_report_plugin_interface import BaseReporterPlugin
class LANGBITEReportPlugin(BaseReporterPlugin):
    def get_template_relative_path(self): return "x.html.j2"
    def build_template_context(self, **kw): return {}
    def generate_content(self, **kw): return "<p>LEGACY-LANGBITE-OUTPUT</p>"
'''


# a legacy {KEY}ReportPlugin in the plugin directory is found by the same keys
def test_legacy_plugins_are_found_by_the_tool_keys(tmp_path):
    (tmp_path / "legacy_langbite.py").write_text(LEGACY)
    reg = build(entry_points=[], plugin_dirs=[tmp_path])
    assert reg.tool_for(LANGBITE) is not None


def test_a_tool_renderer_wins_over_a_legacy_plugin(tmp_path):
    (tmp_path / "legacy_langbite.py").write_text(LEGACY)
    reg = build(entry_points=[ep("plugins_fixture.tools:LangBiTeTool", group="aisc_report.tools")],
                plugin_dirs=[tmp_path])
    chosen = reg.tool_for(LANGBITE)
    Base = need("aisc_report_plugin_interface", "BaseToolRenderer")
    assert isinstance(chosen, Base) or (isinstance(chosen, type) and issubclass(chosen, Base))


def test_two_tool_renderers_for_one_tool_refuse_to_start():
    Duplicate = need(REG, "DuplicateToolRenderer")
    with pytest.raises(Duplicate):
        build(entry_points=[ep("plugins_fixture.tools:LangBiTeTool", group="aisc_report.tools", name="a"),
                            ep("plugins_fixture.tools:BrokenLangBiTeTool", group="aisc_report.tools", name="b")])


def test_two_legacy_plugins_for_one_tool_refuse_to_start(tmp_path):
    Duplicate = need(REG, "DuplicateToolRenderer")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    (a / "legacy_one.py").write_text(LEGACY)
    (b / "legacy_two.py").write_text(LEGACY)
    with pytest.raises(Duplicate):
        build(entry_points=[], plugin_dirs=[a, b])
