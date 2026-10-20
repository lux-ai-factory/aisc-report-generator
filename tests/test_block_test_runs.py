"""Test runs block. Alpha V2 has runs 21, 22 (failed) and 23; the
seed's plugin configs 1 and 2 hold {"api_key": "CONFIGSECRET"}, which the report may never read."""
import pytest

from conftest import block, section, text
from v2_block_helpers import one, render_snapshot, v2_snapshot

pytestmark = pytest.mark.db


def test_summary_is_one_line_per_run_of_the_version(deps):
    t, st, node, _ = one(deps, "test_runs", project="A", system="A_V2")
    assert st["status"] == "ok"
    assert len(node.select("tbody tr")) == 3
    assert "Failed" in t


def test_full_names_each_tools_configuration_never_its_settings(deps):
    t, _, _, result = one(deps, "test_runs", project="A", system="A_V2", detail="full")
    assert "c2" in t                                  # run 21's LangBiTe ran with configuration "c2"
    assert "Started" in t and "Finished" in t
    assert "CONFIGSECRET" not in result["html"]


def test_there_is_no_configuration_option(deps):
    from v2_block_helpers import block_class
    assert set(block_class(deps, "test_runs").options_schema["properties"]) == {"detail"}


def test_no_runs_in_the_period_says_so(deps):
    b = block("test_runs")
    snap = v2_snapshot([b], project="A", system="A_V2", snapshot_version=3,
                       selection={"period_from": "2026-01-01T00:00:00+00:00",
                                  "period_to": "2026-01-02T00:00:00+00:00", "other_versions": False,
                                  "compare_to": None})
    t = text(section(render_snapshot(deps, snap)["html"], b["instance_id"]))
    assert "No test runs between 2026-01-01 and 2026-01-01 for version 2." in t
