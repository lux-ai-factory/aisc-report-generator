"""Filters of the Control objectives and Summary blocks.

The defaults show everything. An objective is shown when its requirement group
is selected, it is selected, and (with a minimum impact) at least one of its mapped risks passes.
A risk passes when its impact is at least the minimum, or when its impact is unrated and unrated risks
are included. The option is stored as min_severity, a name saved layouts already use, but it filters
on the risk's impact.
"""
from __future__ import annotations

from dataclasses import dataclass


def requirement_groups(labels: dict) -> list[str]:
    """The distinct requirement groups (macro strings) in the order of the objectives CSV."""
    out: list[str] = []
    for info in labels.values():
        macro = (info or {}).get("macro") or ""
        if macro and macro not in out:
            out.append(macro)
    return out


@dataclass(frozen=True)
class Filters:
    requirements: object = "all"
    objectives: object = "all"
    min_severity: int | None = None
    include_unrated: bool = True

    @classmethod
    def from_options(cls, options: dict) -> "Filters":
        return cls(requirements=options.get("requirements", "all"), objectives=options.get("objectives", "all"),
                   min_severity=options.get("min_severity"), include_unrated=options.get("include_unrated", True))

    @property
    def active(self) -> bool:
        return self.requirements != "all" or self.objectives != "all" or self.min_severity is not None

    @property
    def narrows_objectives(self) -> bool:
        return self.requirements != "all" or self.objectives != "all"

    def risk_passes(self, risk: dict) -> bool:
        if self.min_severity is None:
            return True
        impact = risk.get("impact")
        if impact is None:
            return bool(self.include_unrated)
        return impact >= self.min_severity

    def objective_shown(self, oid: str, info: dict | None, risks) -> bool:
        if self.requirements != "all" and ((info or {}).get("macro") or "") not in set(self.requirements):
            return False
        if self.objectives != "all" and oid not in set(self.objectives):
            return False
        if self.min_severity is not None and not any(self.risk_passes(r) for r in risks):
            return False
        return True

    def notice(self, t) -> str:
        parts = []
        if self.requirements != "all":
            parts.append(t("requirement groups {groups}", groups=", ".join(self.requirements)))
        if self.objectives != "all":
            parts.append(t("objectives {ids}", ids=", ".join(self.objectives)))
        if self.min_severity is not None:
            if self.include_unrated:
                parts.append(t("risk impact at least {n}, unrated risks included", n=self.min_severity))
            else:
                parts.append(t("risk impact at least {n}", n=self.min_severity))
        return t("Filtered: {parts}.", parts="; ".join(parts))


REQUIREMENTS_PROPERTY = {
    "title": "Requirement groups",
    "description": "Show only the objectives of these requirement groups.",
    "oneOf": [{"const": "all"}, {"type": "array", "items": {"type": "string", "minLength": 1, "x-aisc-prose": False}}],
}
