"""The Key figures block.

Mike v2: release 1.0 of the 18th of September; 5 risks (rated Critical, High, Medium, Low, not rated); 4 objectives in 4 groups;
4 Done evaluations (LangBiTe, StrongREJECT, Promptfoo); checklists cl-m1 (2 of 2, scores 4 and 5) and
cl-m2 (1 of 1, score 3). Markup contract: tiles carry data-figure (see v2_block_helpers).
"""
import pytest

from conftest import assert_no_foreign_data
from v2_block_helpers import (MIKE_MAP, assert_option, block_class, figure, need_tool_package,
                              one)

pytestmark = pytest.mark.db
FIGURES = ["version", "risks", "objectives", "coverage", "tests", "checklists"]


def test_declaration(deps):
    cls = block_class(deps, "key_figures")
    assert cls.title == "Key figures"
    assert set(cls.reads) == {"platform", "qualification", "control_objectives", "engine", "controls"}
    d = cls.full_default_options()
    assert d["figures"] == FIGURES and d["show_tool_headlines"] is True
    assert_option(deps, "key_figures", "figures")


def test_tiles_in_order(deps):
    _, st, node, result = one(deps, "key_figures", coverage_links=MIKE_MAP)
    order = [el["data-figure"] for el in node.find_all(attrs={"data-figure": True}) if el["data-figure"] != "tool"]
    assert order == FIGURES
    assert "M1MARK" not in result["html"]
    assert_no_foreign_data(result["html"])


def test_version_tile(deps):
    _, _, node, _ = one(deps, "key_figures", figures=["version"])
    t = figure(node, "version")
    assert "Version 2" in t and "1.0" in t and "2026-09-18" in t


def test_risks_tile(deps):
    _, _, node, _ = one(deps, "key_figures", figures=["risks"])
    t = figure(node, "risks")
    assert "5" in t
    # counts by rating band (impact x likelihood)
    assert "by rating: Critical: 1, High: 1, Medium: 1, Low: 1, not rated: 1" in t
    assert "severity" not in t


def test_objectives_tile(deps):
    _, _, node, _ = one(deps, "key_figures", figures=["objectives"])
    t = figure(node, "objectives")
    assert "4" in t and "in 4 requirement groups" in t


def test_coverage_tile_reads_the_layout_map(deps):
    _, _, node, _ = one(deps, "key_figures", figures=["coverage"], coverage_links=MIKE_MAP)
    t = figure(node, "coverage")
    assert "2 of 4 objectives with evidence" in t
    assert "no evidence" in t and "not covered" in t


def test_tests_tile(deps):
    _, _, node, _ = one(deps, "key_figures", figures=["tests"], show_tool_headlines=False)
    t = figure(node, "tests")
    assert "4 evaluations" in t
    for tool in ("LangBiTe", "StrongREJECT", "Promptfoo"):
        assert tool in t
    assert node.find(attrs={"data-figure": "tool"}) is None


def test_tool_headline_tiles(deps):
    need_tool_package("aisc_report_plugin_langbite", "LANGBITEToolRenderer")
    need_tool_package("aisc_report_plugin_strongreject", "STRONGREJECTToolRenderer")
    t, _, node, _ = one(deps, "key_figures", figures=["tests"])
    tiles = node.find_all(attrs={"data-figure": "tool"})
    assert tiles, "one tile per headline item of a dedicated renderer"
    assert "LangBiTe: Overall pass rate" in t
    assert "StrongREJECT: " in t
    per_tool = {}
    for el in tiles:
        tool = el.get_text(" ").split(":")[0].strip()
        per_tool[tool] = per_tool.get(tool, 0) + 1
    assert all(n <= 2 for n in per_tool.values()), per_tool


def test_checklists_tile(deps):
    _, _, node, _ = one(deps, "key_figures", figures=["checklists"])
    t = figure(node, "checklists")
    assert "3 of 3 questions answered" in t and "mean score 4" in t and "(1 to 5)" in t


def test_a_figure_without_data_is_na(deps):
    t, st, node, _ = one(deps, "key_figures", project="D", system="D_V1")
    tests = figure(node, "tests")
    assert "n/a" in tests and "version 1" in tests
    assert st["status"] != "empty"


def test_empty_only_when_every_figure_is_na(deps):
    _, st, *_ = one(deps, "key_figures", project="C", system="C_V1",
                    figures=["risks", "objectives", "coverage", "tests", "checklists"])
    assert st["status"] == "empty"


def test_stale_when_a_source_is_newer(deps):
    _, st, *_ = one(deps, "key_figures", project="A", system="A_V2")
    assert st["status"] == "stale" and "Newer results exist for version 3." in st["notices"]
    _, st, *_ = one(deps, "key_figures")
    assert st["status"] == "ok"


def test_unknown_figure_is_invalid(deps):
    cls = block_class(deps, "key_figures")
    assert cls.options_problems({**cls.full_default_options(), "figures": ["version", "weather"]})


# Tool tiles follow the report language.

def _tool_tiles(deps, language):
    from v2_block_helpers import block, render_snapshot, section

    b = block("key_figures", figures=["tests"])
    result = render_snapshot(deps, v2_snapshot_with_language([b], language))
    return None, section(result["html"], b["instance_id"])


def v2_snapshot_with_language(blocks, language):
    from v2_block_helpers import v2_snapshot

    return v2_snapshot(blocks, language=language)


def test_english_tool_tiles_are_unchanged(deps):
    import re

    need_tool_package("aisc_report_plugin_langbite", "LANGBITEToolRenderer")
    _, node = _tool_tiles(deps, "en")
    tiles = " | ".join(" ".join(el.get_text(" ").split()) for el in node.find_all(attrs={"data-figure": "tool"}))
    assert re.search(r"\d\.\d", tiles) and "Overall pass rate" in tiles, tiles


def test_a_contract_2_renderer_whose_headline_takes_only_the_run_still_gets_tiles(deps, monkeypatch):
    """A tool renderer whose headline takes only the run (no context) still gets its tiles."""
    cls = need_tool_package("aisc_report_plugin_langbite", "LANGBITEToolRenderer")
    original = cls.headline

    def headline(self, run):
        return original(self, run)

    monkeypatch.setattr(cls, "headline", headline)
    _, node = _tool_tiles(deps, "fr")          # a snapshot saying "fr" renders English
    tiles = " ".join(el.get_text(" ") for el in node.find_all(attrs={"data-figure": "tool"}))
    assert "Overall pass rate" in tiles, tiles


# "label: value" goes through one message.

def _label_value_sections(deps, language):
    from v2_block_helpers import block, render_snapshot, section

    blocks = [block("key_figures", figures=["version", "risks", "objectives", "coverage", "tests", "checklists"]),
              block("summary_coverage"), block("control_objectives", show_rationale=True),
              block("control_objectives", group_by="risk")]
    result = render_snapshot(deps, v2_snapshot_with_language(blocks, language) | {"coverage_links": MIKE_MAP})
    return {f'{b["block_type"]} {b["options"]}': " ".join(section(result["html"], b["instance_id"]).get_text(" ").split())
            for b in blocks}


def test_english_label_value_texts_are_unchanged(deps):
    pytest.importorskip("aisc_report_plugin_strongreject", reason="optional tool renderer, not installed")
    texts = _label_value_sections(deps, "en")
    kf = next(v for k, v in texts.items() if k.startswith("key_figures"))
    assert "by rating: Critical: 1, High: 1" in kf and "no evidence: 1" in kf and "StrongREJECT: " in kf, kf
