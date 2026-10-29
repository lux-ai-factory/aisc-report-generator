"""The compatibility golden cases: snapshots that use none of the later snapshot keys (document,
selection, language, commentary and the like).

A 7-block layout as the composer stored it, with and without a template's look, on the bed's seed:
- Alpha v2 (A_V2) and Mike v2 (M_V2): evaluations; only the Test results section may change.
- Alpha v2 with legacy coverage links on the first summary block and a second summary block with
  empty links: only the second summary block may change.
"""
from __future__ import annotations

import copy

from conftest import FIXED_NOW, IDS  # noqa: F401  (FIXED_NOW: the time the goldens are rendered at)

LAYOUT_ID = "11111111-1111-4111-8111-111111111111"

LIVE_LAYOUT = [
    ("00000000-0000-4000-8000-00000000a001", "cover", {"show_logo": True, "report_title": "AI system assessment report", "page_break_before": False, "show_generated_by": True}),
    ("00000000-0000-4000-8000-00000000a002", "ai_card", {"show_tags": True, "show_components": True, "show_graph_stats": False, "page_break_before": False}),
    ("00000000-0000-4000-8000-00000000a003", "risk_classification", {"show_chains": True, "page_break_before": False, "show_impact_areas": True, "stated_risk_class": "not_determined"}),
    ("00000000-0000-4000-8000-00000000a004", "control_objectives", {"group_by": "objective", "show_quotes": False, "show_status": True, "show_rationale": True, "page_break_before": False}),
    ("00000000-0000-4000-8000-00000000a005", "test_results", {"tools": "all", "statuses": ["Done"], "show_artifacts": False, "page_break_before": False, "show_measurements": True}),
    ("00000000-0000-4000-8000-00000000a006", "control_answers", {"checklists": "all", "show_scores": True, "show_unanswered": True, "include_archived": False, "page_break_before": False}),
    ("00000000-0000-4000-8000-00000000a007", "summary_coverage", {"links": [], "page_break_before": False, "show_uncovered_only": False}),
]
LIVE_STYLE = {"font": "inter", "font_size_pt": 10, "primary_color": "#000fdf", "accent_color": "#ff007e"}
TEST_RESULTS_IID = "00000000-0000-4000-8000-00000000a005"
SECOND_SUMMARY_IID = "00000000-0000-4000-8000-00000000a008"


def live_blocks():
    return [{"instance_id": i, "block_type": t, "options": copy.deepcopy(o)} for i, t, o in LIVE_LAYOUT]


def legacy_links_blocks():
    b = live_blocks()
    b[6]["options"]["links"] = [{"objective_id": "R1.1", "tests": ["LangBiTe"], "checklists": ["cl-1"]},
                                {"objective_id": "R2.1", "tests": [], "checklists": ["cl-1"]}]
    b.append({"instance_id": SECOND_SUMMARY_IID, "block_type": "summary_coverage",
              "options": {"links": [], "page_break_before": False, "show_uncovered_only": False}})
    return b


CASES = {
    # with evaluations: only the Test results section may differ
    "a_v2_live": {"project": "A", "system": "A_V2", "blocks": live_blocks, "style": None},
    "a_v2_live_styled": {"project": "A", "system": "A_V2", "blocks": live_blocks, "style": LIVE_STYLE, "pdf": True},
    "m_v2_live_styled": {"project": "M", "system": "M_V2", "blocks": live_blocks, "style": LIVE_STYLE},
    # legacy coverage links: only the second summary block may differ
    "a_v2_legacy_links": {"project": "A", "system": "A_V2", "blocks": legacy_links_blocks, "style": LIVE_STYLE},
}


def snapshot_for(case: dict, mode: str) -> dict:
    s = {"project_id": IDS[case["project"]], "system_id": IDS[case["system"]],
         "layout": {"id": LAYOUT_ID, "name": "Live default layout", "revision": 1},
         "blocks": case["blocks"](), "mode": mode, "requested_by": "alice", "snapshot_version": 3}
    if case.get("style"):
        s["style"] = copy.deepcopy(case["style"])
    return s
