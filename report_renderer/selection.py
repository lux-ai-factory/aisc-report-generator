"""The data a report covers, chosen when it is generated.

The anchor version is the snapshot's `system_id`. The selection adds the period of test runs (from
inclusive, to exclusive, UTC), whether runs made against other versions are included, and the version
Changes since compares with. An absent selection is the anchor version alone, all its runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Selection:
    period_from: datetime | None = None
    period_to: datetime | None = None
    other_versions: bool = False
    compare_to: str | None = None


EMPTY = Selection()


def _when(value) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def from_snapshot(d: dict | None) -> Selection:
    if not d:
        return EMPTY
    return Selection(period_from=_when(d.get("period_from")), period_to=_when(d.get("period_to")),
                     other_versions=bool(d.get("other_versions", False)), compare_to=d.get("compare_to") or None)
