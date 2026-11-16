"""The report generator names a project's database with its own copy of the rule (report_renderer.data.scope
.database_name), since it carries no shared code. The copy is held to the shared cases, projectdb-cases.json
(shared/identity of the AISC checkout): a canonical pid names the database the shared rule names, and every pid
the shared rule refuses is refused here too, except three spellings of a pid that the copy reads as that pid
(braces, a urn:uuid: prefix, no hyphens). Those name the same project's own database, never another's.

A checkout of the generator on its own has no cases, and the test says so as a skip."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from report_renderer.data import scope


def _cases_file() -> Path | None:
    named = os.environ.get("AISC_PROJECTDB_CASES")
    if named:
        return Path(named)
    in_checkout = Path(__file__).resolve().parents[3] / "shared/identity/projectdb-cases.json"
    return in_checkout if in_checkout.is_file() else None


CASES_FILE = _cases_file()
NAMES = json.loads(CASES_FILE.read_text())["names"] if CASES_FILE else []
#: what uuid.UUID reads as a pid although the shared rule does not take it
READ_AS_THE_PID = ("{", "urn:uuid:")


def _read_as_the_pid(pid: str) -> bool:
    return pid.startswith(READ_AS_THE_PID) or (len(pid) == 32 and all(c in "0123456789abcdefABCDEF" for c in pid))


@pytest.mark.skipif(CASES_FILE is None, reason="no projectdb-cases.json: the generator is not inside an AISC checkout")
@pytest.mark.parametrize("case", NAMES, ids=lambda c: repr(c["pid"]))
def test_a_pid_names_its_database_as_the_shared_cases_say(case):
    pid = case["pid"]
    if not case.get("refused"):
        assert scope.database_name(pid) == case["name"]
    elif _read_as_the_pid(pid):
        assert scope.database_name(pid) == "project_" + uuid.UUID(pid).hex
    else:
        with pytest.raises(ValueError):
            scope.database_name(pid)
