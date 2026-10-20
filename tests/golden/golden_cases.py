"""The compatibility golden cases: snapshots that use none of the later snapshot keys (document,
selection, language, commentary and the like).

A 7-block layout as the composer stored it, with and without a template's look, on the bed's seed:
- Delta v1 (D_V1): no evaluation at all: the output must stay identical.
- Alpha v2 (A_V2) and Mike v2 (M_V2): evaluations; only the Test results section may change.
- Alpha v2 with legacy coverage links on the first summary block and a second summary block with
  empty links: only the second summary block may change.
- Delta v1 with free text, titles and a page break (plain free text must render unchanged).
"""
from __future__ import annotations

import copy
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "aisc-install/scripts/lib"))
import report_bed  # noqa: E402

IDS = report_bed.IDS
FIXED_NOW = datetime(2026, 9, 20, 10, 30, tzinfo=timezone.utc)
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


def free_text_blocks():
    b = live_blocks()
    b[1]["options"]["title"] = "The card, retitled"
    b[2]["options"]["page_break_before"] = True
    b.insert(1, {"instance_id": "00000000-0000-4000-8000-00000000a009", "block_type": "free_text",
                 "options": {"title": "Scope", "page_break_before": False,
                             "text": "First line <b>not bold</b>\nsecond line\n\nNew paragraph with **stars** and [a](https://e.org)"}})
    return b


CASES = {
    # no evaluation: identical output required
    "d_v1_live": {"project": "D", "system": "D_V1", "blocks": live_blocks, "style": None, "pdf": True},
    "d_v1_live_styled": {"project": "D", "system": "D_V1", "blocks": live_blocks, "style": LIVE_STYLE, "pdf": True},
    "d_v1_free_text": {"project": "D", "system": "D_V1", "blocks": free_text_blocks, "style": LIVE_STYLE},
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
         "blocks": case["blocks"](), "mode": mode, "requested_by": "alice"}
    if case.get("style"):
        s["style"] = copy.deepcopy(case["style"])
    return s
