"""Control objectives block.

Markup the tests rely on: one element per objective carrying `data-objective="<ID>"` (group_by
objective), one per risk carrying `data-risk="<risk_id>"` (group_by risk).
"""
import pytest

from conftest import assert_no_foreign_data, render_one, text

pytestmark = pytest.mark.db

V2_OBJECTIVES = ["R1.1", "R2.1", "R4.1", "R5.1"]
STATUSES = ("not covered", "no evidence", "evidence, attention", "evidence")


def test_each_objective_once_with_its_catalogue_label(deps):
    _, s, node, result = render_one(deps, "control_objectives")
    found = [el["data-objective"] for el in node.find_all(attrs={"data-objective": True})]
    assert sorted(found) == V2_OBJECTIVES
    r11 = text(node.find(attrs={"data-objective": "R1.1"}))
    assert "A qualified operator can monitor and halt the system." in r11 and "AI Act Art. 14" in r11
    r21 = text(node.find(attrs={"data-objective": "R2.1"}))
    assert "Bias against applicants" in r21 and "Opaque refusals" in r21   # both risks mapped to it
    assert_no_foreign_data(result["html"])
    assert "R3.1" not in found


def test_grouped_by_risk(deps):
    _, _, node, _ = render_one(deps, "control_objectives", group_by="risk")
    risks = [el["data-risk"] for el in node.find_all(attrs={"data-risk": True})]
    assert risks == ["R-1", "R-2"]
    r2 = text(node.find(attrs={"data-risk": "R-2"}))
    for oid in ("R2.1", "R4.1", "R5.1"):
        assert oid in r2
    assert "R1.1" not in r2


def test_rationale_and_quotes(deps):
    t, *_ = render_one(deps, "control_objectives")
    assert "oversight counters bias" in t and "quote one" not in t
    t, *_ = render_one(deps, "control_objectives", show_rationale=False, show_quotes=True)
    assert "oversight counters bias" not in t and "quote one" in t


def test_status_per_objective(deps):
    _, _, node, _ = render_one(deps, "control_objectives")
    for oid in V2_OBJECTIVES:
        el_text = text(node.find(attrs={"data-objective": oid}))
        assert any(st in el_text for st in STATUSES), oid
    _, _, node, _ = render_one(deps, "control_objectives", show_status=False)
    for oid in V2_OBJECTIVES:
        el_text = text(node.find(attrs={"data-objective": oid}))
        assert not any(st in el_text for st in STATUSES), oid


def test_a_mapping_run_that_did_not_stop_clean(deps):
    _, s, _, _ = render_one(deps, "control_objectives")
    assert "The mapping run stopped: cap." in s["notices"]
    _, s, _, _ = render_one(deps, "control_objectives", system="A_V1")
    assert not any(n.startswith("The mapping run stopped") for n in s["notices"])


def test_no_assessment_for_the_version(deps):
    _, s, _, _ = render_one(deps, "control_objectives", project="C", system="C_V1")
    assert s["status"] == "empty"


def test_stale_when_a_newer_assessment_exists(deps):
    t, s, _, _ = render_one(deps, "control_objectives", system="A_V1")
    assert s["status"] == "stale" and "Newer results exist for version 2." in s["notices"]
    assert "R3.1" in t and "R1.1" not in t
