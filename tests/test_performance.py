"""Modest performance limits, with the fake Superset."""
import time

import pytest

from conftest import IDS, block, render

pytestmark = pytest.mark.db


def twenty():
    kinds = [("cover", {}), ("ai_card", {}), ("risk_classification", {}), ("control_objectives", {}),
             ("test_results", {}), ("control_answers", {}), ("summary_coverage", {}), ("free_text", {"text": "t"})]
    blocks = [block(k, **o) for k, o in kinds]
    blocks += [block("dashboard_chart", chart_id=IDS["CHART_A"]) for _ in range(6)]
    blocks += [block(k, **o) for k, o in kinds[1:7]]
    assert len(blocks) == 20
    return blocks


def test_a_20_block_preview_within_10_seconds(deps):
    t0 = time.monotonic()
    render(deps, twenty())
    assert time.monotonic() - t0 < 10


def test_a_20_block_pdf_within_60_seconds(deps):
    t0 = time.monotonic()
    render(deps, twenty(), mode="pdf")
    assert time.monotonic() - t0 < 60
