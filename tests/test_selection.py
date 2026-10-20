"""The report's data selection, as the snapshot gives it."""
from datetime import datetime, timezone

from conftest import need, snapshot


def test_an_absent_selection_is_the_anchor_version_alone():
    sel = need("report_renderer.selection", "from_snapshot")(None)
    assert (sel.period_from, sel.period_to, sel.other_versions, sel.compare_to) == (None, None, False, None)


def test_a_selection_is_read_from_its_iso_strings():
    sel = need("report_renderer.selection", "from_snapshot")(
        {"period_from": "2026-09-10T00:00:00+00:00", "period_to": "2026-09-11T00:00:00+00:00",
         "other_versions": True, "compare_to": "a1000000-0000-4000-8000-000000000001"})
    assert sel.period_from == datetime(2026, 9, 10, tzinfo=timezone.utc)
    assert sel.period_to == datetime(2026, 9, 11, tzinfo=timezone.utc)
    assert sel.other_versions is True and sel.compare_to == "a1000000-0000-4000-8000-000000000001"


def test_the_snapshot_schema_takes_a_selection_and_version_3():
    validate = need("report_renderer.snapshot", "validate")
    s = snapshot([], project="A", system="A_V2", mode="preview")
    s["snapshot_version"] = 3
    s["selection"] = {"period_from": None, "period_to": "2026-09-11T00:00:00+00:00", "other_versions": False,
                      "compare_to": None}
    assert validate(s) == []
    s["selection"]["colour"] = "red"
    assert validate(s) != []                       # nothing else in a selection


def test_the_fingerprint_changes_with_the_selection():
    fp = need("report_renderer.snapshot", "fingerprint")
    a = snapshot([], project="A", system="A_V2", mode="pdf")
    b = {**a, "selection": {"period_from": "2026-09-10T00:00:00+00:00", "period_to": None,
                            "other_versions": False, "compare_to": None}}
    assert fp(a) != fp(b)
