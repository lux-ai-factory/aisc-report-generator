"""The snapshot the composer sends.

`report_renderer.snapshot.validate(snapshot) -> [ {instance_id, code, pointer, message} ]`.
"""
import copy

import pytest

from conftest import IDS, block, need, snapshot


def validate(s):
    return need("report_renderer.snapshot", "validate")(s)


def good():
    return snapshot([block("free_text", text="hello"), block("cover")])


def test_a_good_snapshot_has_no_problems():
    assert validate(good()) == []


@pytest.mark.parametrize(
    "mutate,pointer",
    [
        (lambda s: s.pop("project_id"), "/project_id"),
        (lambda s: s.update(system_id="not-a-uuid"), "/system_id"),
        (lambda s: s.update(mode="word"), "/mode"),  # docx is a valid mode, word is not
        (lambda s: s["blocks"][0].pop("instance_id"), "/blocks/0/instance_id"),
        (lambda s: s["blocks"][1].update(block_type=7), "/blocks/1/block_type"),
        (lambda s: s["blocks"][1].update(options="x"), "/blocks/1/options"),
        (lambda s: s["layout"].pop("revision"), "/layout/revision"),
    ],
)
def test_problems_carry_the_json_pointer(mutate, pointer):
    s = good()
    mutate(s)
    problems = validate(s)
    assert problems, "expected a problem"
    assert pointer in [p["pointer"] for p in problems]
    for p in problems:
        assert set(p) == {"instance_id", "code", "pointer", "message"}


def test_instance_ids_are_unique():
    s = good()
    s["blocks"][1]["instance_id"] = s["blocks"][0]["instance_id"]
    problems = validate(s)
    assert any(p["pointer"] == "/blocks/1/instance_id" for p in problems)


def test_the_problem_names_the_instance():
    s = good()
    iid = s["blocks"][1]["instance_id"]
    s["blocks"][1]["options"] = "x"
    assert [p["instance_id"] for p in validate(s)] == [iid]


def test_validation_does_not_change_the_snapshot():
    s = good()
    before = copy.deepcopy(s)
    validate(s)
    assert s == before and s["project_id"] == IDS["A"]


# The period is a date-time with its time zone: "format": "date-time" was not
# checked, so "yesterday" passed and crashed the render (500), and a naive value broke the comparison
# with comments' aware times.

@pytest.mark.parametrize("value", ["yesterday", "2026-09-13T00:00:00", "2026-13-01T00:00:00+00:00"])
def test_a_period_that_is_not_a_zoned_date_time_is_a_problem(value):
    from conftest import block, snapshot, window

    s = snapshot([block("free_text", text="x")], selection=window("2026-09-01", "2026-10-01"))
    s["selection"]["period_from"] = value
    problems = need("report_renderer.snapshot", "validate")(s)
    assert [p["pointer"] for p in problems] == ["/selection/period_from"]


def test_a_zoned_period_has_no_problem():
    from conftest import block, snapshot, window

    s = snapshot([block("free_text", text="x")], selection=window("2026-09-01", "2026-10-01"))
    assert need("report_renderer.snapshot", "validate")(s) == []
