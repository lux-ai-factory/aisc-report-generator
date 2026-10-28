"""Control objectives and Summary filters.

Mike v2 (seed_tools.sql), risks as (impact, likelihood): R-1 (5, 4) -> R1.1, R-2 (3, unrated) -> R2.1,
R-3 (1, 2) -> R4.1, R-4 not rated -> R5.1, R-5 (4, unrated) maps to nothing. The option min_severity
keeps its name for stored layouts and filters on the risk's impact. The objectives fixture CSV has 5 objectives in
5 requirement groups (R1 to R5), not the live catalogue's 50 in 11.
"""
import pytest

from conftest import IDS, need
from v2_block_helpers import (MIKE_MAP, REQUIREMENT_GROUPS, assert_option, block_class, objectives_shown, one, risks_shown)

pytestmark = pytest.mark.db


# Options and defaults.

def test_new_options_default_to_everything(deps):
    for name in ("requirements", "objectives", "min_severity", "include_unrated", "show_severity"):
        assert_option(deps, "control_objectives", name)
    d = block_class(deps, "control_objectives").full_default_options()
    assert d["requirements"] == "all" and d["objectives"] == "all"
    assert d["min_severity"] is None and d["include_unrated"] is True and d["show_severity"] is False


def test_defaults_render_as_today(deps):
    t, st, node, _ = one(deps, "control_objectives")
    t2, st2, node2, _ = one(deps, "control_objectives", requirements="all", objectives="all", min_severity=None,
                            include_unrated=True, show_severity=False)
    assert objectives_shown(node) == objectives_shown(node2) == ["R1.1", "R2.1", "R4.1", "R5.1"]
    assert t == t2
    assert not any(n.startswith("Filtered") for n in st2["notices"])


def test_requirement_choices_in_catalogue_order(deps):
    ctx = need("report_renderer.context", "context_for")(IDS["M"], IDS["M_V2"], deps=deps, mode="preview")
    choices = block_class(deps, "control_objectives")().choices(ctx, "requirements")
    assert [c["value"] for c in choices] == REQUIREMENT_GROUPS


def test_objective_choices_of_the_version(deps):
    ctx = need("report_renderer.context", "context_for")(IDS["M"], IDS["M_V2"], deps=deps, mode="preview")
    choices = block_class(deps, "control_objectives")().choices(ctx, "objectives")
    assert [c["value"] for c in choices] == ["R1.1", "R2.1", "R4.1", "R5.1"]
    assert choices[0]["label"] == "R1.1 Operator oversight capability"


# The filters.

def test_requirement_group_filter(deps):
    _, st, node, _ = one(deps, "control_objectives", requirements=["R1 Human Agency and Oversight", "R4 Accuracy"])
    assert objectives_shown(node) == ["R1.1", "R4.1"]


def test_objective_filter(deps):
    _, _, node, _ = one(deps, "control_objectives", objectives=["R2.1", "R5.1"])
    assert objectives_shown(node) == ["R2.1", "R5.1"]


def test_min_severity_keeps_unrated_by_default(deps):
    _, _, node, _ = one(deps, "control_objectives", min_severity=3)
    assert objectives_shown(node) == ["R1.1", "R2.1", "R5.1"]


def test_min_severity_without_unrated(deps):
    _, _, node, _ = one(deps, "control_objectives", min_severity=3, include_unrated=False)
    assert objectives_shown(node) == ["R1.1", "R2.1"]


def test_group_by_risk_with_severity(deps):
    _, _, node, _ = one(deps, "control_objectives", group_by="risk", min_severity=4)
    # R-1 (5) and R-4 (unrated, its objective R5.1 is shown); R-5 (4) has no objective and no objective filter is set
    assert risks_shown(node) == ["R-1", "R-4", "R-5"]


def test_group_by_risk_with_an_objective_filter_hides_unmapped_risks(deps):
    _, _, node, _ = one(deps, "control_objectives", group_by="risk", objectives=["R1.1"])
    assert risks_shown(node) == ["R-1"]


def test_all_filters_combine(deps):
    _, _, node, _ = one(deps, "control_objectives", requirements=["R1 Human Agency and Oversight", "R2 Data Governance"],
                        objectives=["R2.1", "R4.1"], min_severity=2)
    assert objectives_shown(node) == ["R2.1"]


def test_severity_out_of_range_is_invalid(deps):
    cls = block_class(deps, "control_objectives")
    assert_option(deps, "control_objectives", "min_severity")
    for bad in (0, 6, "high"):
        assert cls.options_problems({**cls.full_default_options(), "min_severity": bad})


# Severity shown.

def test_show_severity(deps):
    """show_severity shows the rating (impact x likelihood, an unrated part counting 3)."""
    t, *_ = one(deps, "control_objectives", group_by="risk", show_severity=True)
    assert "Impact 5, likelihood 4: rating 20 (Critical)" in t
    assert "Impact 3, likelihood not rated: rating 9 (Medium)" in t
    assert "Impact 1, likelihood 2: rating 2 (Low)" in t
    assert "Impact 4, likelihood not rated: rating 12 (High)" in t
    assert "Not rated" in t
    assert "Severity" not in t
    t, *_ = one(deps, "control_objectives", group_by="risk")
    assert "rating" not in t and "Not rated" not in t


def test_show_severity_by_objective(deps):
    t, *_ = one(deps, "control_objectives", show_severity=True)
    assert "(Impact 5, likelihood 4: rating 20 (Critical))" in t and "(Not rated)" in t


def test_rating_option_titles(deps):
    props = block_class(deps, "control_objectives").full_options_schema()["properties"]
    assert props["min_severity"]["title"] == "Minimum risk impact"
    assert "impact" in props["min_severity"]["description"].lower()
    assert (props["min_severity"]["minimum"], props["min_severity"]["maximum"]) == (1, 5)
    assert props["show_severity"]["title"] == "Show rating"
    assert "severity" not in " ".join(p.get("description", "") + p.get("title", "")
                                      for p in props.values()).lower()


def test_rating_filter_notice_names_impact(deps):
    _, st, *_ = one(deps, "control_objectives", min_severity=4)
    assert "Filtered: risk impact at least 4, unrated risks included." in st["notices"], st["notices"]


# Filtered notice and nothing left.

def test_a_filter_adds_the_filtered_notice(deps):
    t, st, *_ = one(deps, "control_objectives", min_severity=4)
    assert any(n.startswith("Filtered: ") and n.endswith(".") for n in st["notices"]), st["notices"]


def test_filters_that_hide_everything(deps):
    t, st, node, _ = one(deps, "control_objectives", requirements=["R3 Record Keeping"])
    assert st["status"] == "ok"
    assert "No objective matches the filters of this section." in t
    assert any(n.startswith("Filtered: ") for n in st["notices"])
    assert objectives_shown(node) == []


# summary_coverage requirements.

def test_summary_shows_only_the_filtered_objectives(deps):
    assert_option(deps, "summary_coverage", "requirements")
    t, st, node, _ = one(deps, "summary_coverage", links=MIKE_MAP,
                         requirements=["R1 Human Agency and Oversight", "R5 Transparency"])
    assert objectives_shown(node) == ["R1.1", "R5.1"]
    assert any(n.startswith("Filtered: ") for n in st["notices"])


def test_summary_requirements_default_all(deps):
    assert block_class(deps, "summary_coverage").full_default_options().get("requirements") == "all", \
        "missing feature: summary_coverage.requirements default all"


# No severity on risk classification.

def test_risk_classification_has_no_severity_option(deps):
    """Qualification risks carry no severity, so this block has no severity filter."""
    props = block_class(deps, "risk_classification").full_options_schema()["properties"]
    assert not any("severity" in name for name in props)
