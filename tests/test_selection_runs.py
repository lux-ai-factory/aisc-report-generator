"""Runs in a period, of the anchor version or of all versions.

Project Alpha: V1 from 09-01, V2 from 09-08, V3 from 09-15; runs 11 (V1, 09-02, MLAReject + LangBiTe),
23 (V2, 09-09), 21 (V2, 09-10, LangBiTe + Mystery), 22 (V2, 09-11, failed), 41 and 42 (no version,
09-12), 31 (V3, 09-16)."""
import pytest

from conftest import block, section, text
from v2_block_helpers import render_snapshot, v2_snapshot

pytestmark = pytest.mark.db


def _sel(**over):
    return {"period_from": None, "period_to": None, "other_versions": False, "compare_to": None, **over}


def _text(deps, block_type, sel, **options):
    b = block(block_type, **options)
    snap = v2_snapshot([b], project="A", system="A_V2", snapshot_version=3, selection=sel)
    return text(section(render_snapshot(deps, snap)["html"], b["instance_id"]))


def test_without_a_selection_every_run_of_the_anchor_version(deps):
    t = _text(deps, "test_results", _sel(), detail="summary")
    assert "Mystery" in t and "MLA-Reject" not in t         # V1's MLA-Reject is not there


def test_the_last_day_of_the_period_is_included(deps):
    t = _text(deps, "test_results", _sel(period_from="2026-09-10T00:00:00+00:00",
                                         period_to="2026-09-11T00:00:00+00:00"), detail="summary")
    assert "Mystery" in t                   # run 21 of 09-10 09:00, the one day of the period


def test_a_period_leaves_out_runs_outside_it(deps):
    t = _text(deps, "test_results", _sel(period_from="2026-09-11T00:00:00+00:00",
                                         period_to="2026-09-12T00:00:00+00:00"), detail="summary")
    assert "Mystery" not in t               # only run 22 (09-11, LangBiTe, failed) is in the period


def test_other_versions_brings_their_runs_marked_with_their_version(deps):
    t = _text(deps, "test_results", _sel(other_versions=True), detail="summary")
    assert "MLA-Reject" in t and "(version 1)" in t
    assert "(no version)" in t              # runs 41 and 42 have no version


def test_the_cover_says_when_other_versions_are_included(deps):
    assert "Includes test runs made against other versions." in _text(deps, "cover", _sel(other_versions=True))
    assert "Includes test runs made against other versions." not in _text(deps, "cover", _sel())
