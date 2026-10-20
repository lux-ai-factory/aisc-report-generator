"""Options that named one run or one version leave the layout; the report's selection gives them."""
import pytest

from conftest import IDS, window
from v2_block_helpers import block_class, one

pytestmark = pytest.mark.db


def test_test_results_has_no_evaluations_option(deps):
    assert "evaluations" not in block_class(deps, "test_results").options_schema["properties"]


def test_changes_since_only_names_the_version_before(deps):
    assert block_class(deps, "changes_since").options_schema["properties"]["compare_to"]["enum"] == ["previous"]


def test_changes_since_compares_with_the_selections_version(deps):
    t, *_ = one(deps, "changes_since", project="A", system="A_V3", selection=window(compare_to=IDS["A_V1"]))
    assert "with version 1." in t


def test_changes_since_reads_both_versions_whole_whatever_the_period(deps):
    whole, *_ = one(deps, "changes_since", project="A", system="A_V3", sections=["tests"])
    narrowed, *_ = one(deps, "changes_since", project="A", system="A_V3", sections=["tests"],
                       selection=window("2026-01-01", "2026-01-02"))
    assert narrowed == whole
