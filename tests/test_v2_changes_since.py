"""The Changes since block: what changed since an earlier version.

Mike v2 against v1 (seed_tools.sql): release 0.9 -> 1.0, card description changed, tag "support" added,
component "Example FAQ" added, qualification risk "Biased answers" added; objectives R2.1, R4.1, R5.1
added and R3.1 removed, risks R-2..R-5 added and R-9 removed, R-1 rating 9 -> 20
(impact x likelihood 3 x 3 -> 5 x 4); StrongREJECT
Harmfulness 0.3 -> 0.2 (latest Done run), Promptfoo only in version 2; checklist "Example Assistant transparency"
answered 1 of 2 (mean 2) -> 2 of 2 (mean 4.5), "Example Assistant oversight" only in version 2.
Markup contract: parts carry data-changes (see v2_block_helpers).
"""
import re

import pytest

from conftest import IDS, assert_no_foreign_data, need, window
from v2_block_helpers import MIKE_MAP, block_class, changes_part, one

pytestmark = pytest.mark.db


def test_declaration(deps):
    cls = block_class(deps, "changes_since")
    assert cls.title == "Changes since an earlier version"
    assert set(cls.reads) == {"platform", "qualification", "control_objectives", "engine", "controls"}


def test_options_and_defaults(deps):
    d = block_class(deps, "changes_since").full_default_options()
    assert d["compare_to"] == "previous"
    assert d["sections"] == ["card", "objectives", "tests", "controls"]
    assert d["show_unchanged"] is False


# The base version is checked.

def test_for_version_returns_scoped_data_of_the_earlier_version(deps):
    ctx = need("report_renderer.context", "context_for")(IDS["M"], IDS["M_V2"], deps=deps, mode="preview")
    for_version = getattr(ctx.data, "for_version", None)
    if for_version is None:
        pytest.fail("missing feature: ScopedData.for_version", pytrace=False)
    base = for_version(IDS["M_V1"])
    assert base.system_id == IDS["M_V1"] and base.system_number == 1


@pytest.mark.parametrize("other", ["A_V1", "M_V2"])
def test_for_version_refuses_other_projects_and_later_versions(deps, other):
    NotInProject = need("report_renderer.data.scope", "NotInProject")
    ctx = need("report_renderer.context", "context_for")(IDS["M"], IDS["M_V2"], deps=deps, mode="preview")
    for_version = getattr(ctx.data, "for_version", None)
    if for_version is None:
        pytest.fail("missing feature: ScopedData.for_version", pytrace=False)
    with pytest.raises(NotInProject):
        for_version(IDS[other])


@pytest.mark.parametrize("project,system,compare_to", [("M", "M_V2", "A_V1"), ("M", "M_V1", "M_V2")])
def test_a_bad_base_version_is_an_error_box(deps, project, system, compare_to):
    t, st, _, result = one(deps, "changes_since", project=project, system=system, selection=window(compare_to=IDS[compare_to]),
                           allow_error=True)
    assert "Unknown block type" not in " ".join(st["notices"]), "missing feature: built-in block type changes_since"
    assert st["status"] == "error"
    assert "The version to compare with is not an earlier version of this project." in t
    assert "V1MARK" not in result["html"]


# No earlier version.

@pytest.mark.parametrize("project,system", [("M", "M_V1"), ("D", "D_V1")])
def test_no_earlier_version(deps, project, system):
    t, st, *_ = one(deps, "changes_since", project=project, system=system)
    assert st["status"] == "empty" and "No earlier version to compare with." in t


# First line, never stale.

def test_first_line_and_never_stale(deps):
    t, st, node, _ = one(deps, "changes_since")
    assert "This section compares version 2 (this report) with version 1." in t
    _, st, _, result = one(deps, "changes_since", project="A", system="A_V2")   # version 3 is newer
    assert st["status"] == "ok"
    assert_no_foreign_data(result["html"], markers=("V3MARK", "NULLMARK", "BETAMARK"))


def test_previous_is_the_version_below(deps):
    t, *_ = one(deps, "changes_since", project="A", system="A_V3")
    assert "This section compares version 3 (this report) with version 2." in t
    t, *_ = one(deps, "changes_since", project="A", system="A_V3", selection=window(compare_to=IDS["A_V1"]))
    assert "with version 1." in t


# Card.

def test_card_changes(deps):
    _, _, node, _ = one(deps, "changes_since", sections=["card"])
    t = changes_part(node, "card")
    assert "0.9" in t and "1.0" in t                                          # release
    assert "Answers questions from users M1MARK" in t and "Answers questions from users about services" in t
    assert "support" in t                                                    # tag added
    assert "Example FAQ" in t                                                # component added
    assert "Biased answers" in t                                              # qualification risk added
    assert "Example Provider" not in t                                       # unchanged, left out
    assert node.find(attrs={"data-changes": "tests"}) is None


def test_show_unchanged(deps):
    _, _, node, _ = one(deps, "changes_since", sections=["card"], show_unchanged=True)
    assert "Example Provider" in changes_part(node, "card")


# Objectives.

def test_objectives_and_risks_added_and_removed(deps):
    _, _, node, _ = one(deps, "changes_since", sections=["objectives"])
    t = changes_part(node, "objectives")
    for oid in ("R2.1", "R4.1", "R5.1", "R3.1"):
        assert oid in t
    assert "Automatic logs" in t                     # R3.1's label (removed)
    assert "OldM1" in t                              # R-9 removed, by short label
    assert "Unmapped" in t                           # R-5 added


def test_rating_change_9_to_20(deps):
    """A risk's change is shown as its rating change (impact x likelihood)."""
    _, _, node, _ = one(deps, "changes_since", sections=["objectives"])
    assert "Customer support: rating 9 to 20" in changes_part(node, "objectives")


def test_coverage_status_change_with_the_same_map(deps):
    _, _, node, _ = one(deps, "changes_since", sections=["objectives"], coverage_links=MIKE_MAP)
    t = changes_part(node, "objectives")
    # R1.1: version 1 has cl-m1 mean 2 (below 3): evidence, attention; version 2 mean 4.5: evidence
    assert re.search(r"R1\.1.*evidence, attention.*evidence", t), t[:800]


# Tests.

def test_tests_per_tool_and_metric(deps):
    _, _, node, _ = one(deps, "changes_since", sections=["tests"])
    t = changes_part(node, "tests")
    assert re.search(r"StrongREJECT Harmfulness.*0\.3.*0\.2.*-0\.1", t), t[:800]
    assert "only in version 2" in t                   # Promptfoo and Harmfulness | pair
    for word in ("better", "worse", "improved", "regressed"):
        assert word not in t.lower()


def test_done_evaluation_counts(deps):
    _, _, node, _ = one(deps, "changes_since", sections=["tests"])
    t = changes_part(node, "tests")
    assert "Promptfoo" in t and "StrongREJECT" in t and "LangBiTe" in t


# Controls.

def test_controls_per_checklist(deps):
    _, _, node, _ = one(deps, "changes_since", sections=["controls"])
    t = changes_part(node, "controls")
    assert "answered 1 of 2" in t and "answered 2 of 2" in t
    assert "Example Assistant oversight" in t and "only in version 2" in t


# Nothing changed.

def test_version_one_data_is_allowed_only_in_this_block(deps):
    _, _, _, result = one(deps, "changes_since")
    assert "M1MARK" in result["html"]
    assert_no_foreign_data(result["html"], markers=("BETAMARK", "V1MARK", "V3MARK", "NULLMARK"))
