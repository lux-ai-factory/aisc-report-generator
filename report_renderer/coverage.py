"""The coverage rule shared by the Control objectives and Summary blocks.

An objective is `not covered` when no link names a test or checklist for it; `no evidence` when
none of its linked tests or checklists has data for the pinned version; `evidence` otherwise, and
`evidence, attention` when a linked tool's verdict is fail or a linked checklist's mean score is
below 3 (ATTENTION_BELOW). Computed from the version's data, never from other blocks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from aisc_report_plugin_interface import normalise_tool_name, tool_keys

from .errors import new_error_ref
from .views import load_answers, load_runs

logger = logging.getLogger(__name__)

STATUSES = ("evidence", "evidence, attention", "no evidence", "not covered")
ATTENTION_BELOW = 3


@dataclass(frozen=True)
class Coverage:
    objective_id: str
    status: str
    #: (name, has_data)
    tests: tuple
    #: (id, title, has_data, mean)
    checklists: tuple


def _merged(objective_ids, links) -> dict[str, dict]:
    merged = {oid: {"tests": [], "checklists": []} for oid in objective_ids}
    for link in links or ():
        oid = link.get("objective_id")
        if oid not in merged:
            continue
        for key in ("tests", "checklists"):
            for v in link.get(key) or ():
                if v not in merged[oid][key]:
                    merged[oid][key].append(v)
    return merged


def _link_keys(name) -> set:
    """A link names a plugin by its display name (older maps) or its package (step 4 links)."""
    return {normalise_tool_name(name)} | tool_keys(package_name=name)


def tool_label(name, plugins) -> str:
    """The label of a linked test: the display name of the plugin it names, or the name itself."""
    keys = _link_keys(name)
    for p in plugins:
        if p.get("display_name") and keys & tool_keys(p["display_name"], p.get("name"), p.get("package_name")):
            return p["display_name"]
    return name


def coverage_for(ctx, objective_ids, links) -> dict[str, Coverage]:
    merged = _merged(objective_ids, links)
    any_test = any(m["tests"] for m in merged.values())
    any_list = any(m["checklists"] for m in merged.values())
    # evidence for the pinned version only: with other versions in the report's selection, a run against
    # another version is shown, but it assessed something else
    pinned = ctx.system.get("number")
    runs = [rv for ev in load_runs(ctx, statuses=["Done"]).evaluations
            if ev.evaluation.get("version_number") == pinned for rv in ev.runs] if any_test else []
    answers = {ca.checklist["id"]: ca for ca in load_answers(ctx).checklists} if any_list else {}
    out = {}
    for oid, m in merged.items():
        tests, lists, attention = [], [], False
        for name in m["tests"]:
            keys = _link_keys(name)
            matching = [rv for rv in runs
                        if keys & tool_keys(rv.tool.get("display_name"), rv.tool.get("name"),
                                            rv.tool.get("package_name"))]
            tests.append((name, bool(matching)))
            for rv in matching:
                renderer = ctx.data.tools.tool_for(rv.tool)
                if renderer is not None:
                    try:
                        if renderer.verdict(rv.run) == "fail":
                            attention = True
                    except Exception:                                # noqa: BLE001 (a plugin's code)
                        # the objective keeps "evidence"; the failure is in the log, as in Test results
                        ref = new_error_ref()
                        logger.error("verdict of tool renderer for %s failed, ref %s", name, ref, exc_info=True)
        for cid in m["checklists"]:
            ca = answers.get(cid)
            has = bool(ca and ca.answered)
            mean = ca.mean if ca else None
            lists.append((cid, ca.checklist["title"] if ca else cid, has, mean))
            if has and mean is not None and mean < ATTENTION_BELOW:
                attention = True
        if not tests and not lists:
            status = "not covered"
        elif not any(t[1] for t in tests) and not any(c[2] for c in lists):
            status = "no evidence"
        else:
            status = "evidence, attention" if attention else "evidence"
        out[oid] = Coverage(objective_id=oid, status=status, tests=tuple(tests), checklists=tuple(lists))
    return out
