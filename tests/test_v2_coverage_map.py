"""One coverage map per layout, read by every coverage consumer.

Mike v2 with MIKE_MAP: R1.1 evidence, R2.1 evidence, R4.1 no evidence, R5.1 not covered.
"""
import pytest

from conftest import block, section, text
from v2_block_helpers import MIKE_MAP, MIKE_V2_STATUSES, render_snapshot, v2_snapshot

pytestmark = pytest.mark.db


def status_word(row_text):
    for st in ("evidence, attention", "not covered", "no evidence", "evidence"):
        if st in row_text:
            return st
    return None


def statuses(node):
    return {el["data-objective"]: status_word(text(el)) for el in node.find_all(attrs={"data-objective": True})}


# The summary shows no coverage any more; which map it reads shows in what "only objectives without evidence" keeps.
WITHOUT_EVIDENCE = sorted(o for o, st in MIKE_V2_STATUSES.items() if st in ("not covered", "no evidence"))


def kept(node):
    return sorted(el["data-objective"] for el in node.find_all(attrs={"data-objective": True}))


# The snapshot's map.

def test_control_objectives_read_the_snapshot_map(deps):
    b = block("control_objectives")
    result = render_snapshot(deps, v2_snapshot([b], coverage_links=MIKE_MAP))
    assert statuses(section(result["html"], b["instance_id"])) == MIKE_V2_STATUSES


def test_the_snapshot_map_wins_over_the_first_summary(deps):
    co, summary = block("control_objectives"), block("summary_coverage", links=MIKE_MAP)
    result = render_snapshot(deps, v2_snapshot([co, summary], coverage_links=[]))
    got = statuses(section(result["html"], co["instance_id"]))
    assert set(got.values()) == {"not covered"}, got


def test_summary_with_empty_links_reads_the_snapshot_map(deps):
    b = block("summary_coverage", links=[], show_uncovered_only=True)
    result = render_snapshot(deps, v2_snapshot([b], coverage_links=MIKE_MAP))
    assert kept(section(result["html"], b["instance_id"])) == WITHOUT_EVIDENCE


def test_an_old_snapshot_keeps_the_first_summary_rule(deps):
    """Without coverage_links in the snapshot, the first summary block's links are the map."""
    co, summary = block("control_objectives"), block("summary_coverage", links=MIKE_MAP)
    result = render_snapshot(deps, v2_snapshot([co, summary]))
    assert statuses(section(result["html"], co["instance_id"])) == MIKE_V2_STATUSES


# A summary with its own links.

def test_own_links_win(deps):
    own = [{"objective_id": "R5.1", "tests": ["StrongREJECT"], "checklists": []}]
    b = block("summary_coverage", links=own, show_uncovered_only=True)
    result = render_snapshot(deps, v2_snapshot([b], coverage_links=MIKE_MAP))
    # by its own links only R5.1 has evidence; by the snapshot's map R1.1 and R2.1 would too
    assert kept(section(result["html"], b["instance_id"])) == ["R1.1", "R2.1", "R4.1"]


def test_a_later_summary_with_empty_links_uses_the_layout_map_in_an_old_snapshot(deps):
    """In an old snapshot the layout's map is the first summary block's links."""
    first, second = block("summary_coverage", links=MIKE_MAP), block("summary_coverage", links=[], show_uncovered_only=True)
    result = render_snapshot(deps, v2_snapshot([first, second]))
    assert kept(section(result["html"], second["instance_id"])) == WITHOUT_EVIDENCE


def test_links_option_stays_in_the_schema(deps):
    """Old layouts with links still validate."""
    cls = deps.registry.block("summary_coverage")
    assert cls.options_problems({**cls.full_default_options(), "links": MIKE_MAP}) == []
