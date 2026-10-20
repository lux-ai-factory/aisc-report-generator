"""The Changes since block: what differs from an earlier version.

The report stays of its pinned version S; this block compares it with an earlier version B of the same
project that the editor picks ("previous" by default). Both sides are read with the same readers, each
scoped to its own version. Only neutral words are used: a change is never called better or worse.
"""
from __future__ import annotations

import dataclasses

from markupsafe import Markup, escape
from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult

from ..coverage import coverage_for
from ..data.vocab import TAG_CLASSES, vair_label
from ..data.scope import NotInProject
from ..objective_order import objective_order
from ..views import load_answers, load_runs, selection_of
from ..selection import EMPTY
from ._common import empty_result

SECTIONS = ["card", "objectives", "tests", "controls"]
SECTION_LABELS = {"card": "AI card and version", "objectives": "Control objectives", "tests": "Test results",
                  "controls": "Checklist answers"}
CUT = 300
MAX_TEST_ROWS = 200
VERSION_FIELDS = (("name", "Version name"), ("version", "Release"), ("provider", "Provider"),
                  ("description", "Version description"))
CARD_FIELDS = (("system_name", "System"), ("company", "Company"), ("description", "Description"),
               ("target_use_case", "Target use case"), ("target_users", "Target users"),
               ("intended_deployers", "Intended deployers"))
TAG_FIELDS = (("target_system_tags", "Target system"), ("sector_tags", "Sector"),
              ("market_form_tags", "Market form"), ("locality_tags", "Locality"))


# pure helpers, tested without a database

def cut(text, n: int = CUT) -> str:
    if text is None:
        return ""
    text = str(text)
    return text if len(text) <= n else text[:n] + "..."


def tag_text(values, key: str, vocab: dict) -> str:
    """A tag set as its VAIR labels, sorted; a value that is not a term shows itself."""
    return ", ".join(sorted(vair_label(vocab, TAG_CLASSES[key], v) for v in values))


def previous_version(older: list[dict]) -> dict | None:
    """The highest numbered version below the pinned one (numbers may have gaps)."""
    return max(older, key=lambda v: v["number"]) if older else None


def _signed(value: float) -> str:
    text = f"{value:+.3g}"
    return "0" if text in ("+0", "-0") else text


def compare_metrics(before: dict, after: dict, *, show_unchanged: bool) -> tuple[list[dict], int]:
    """Rows per (tool, metric), ordered by tool then metric; at most 200, and how many more."""
    rows = []
    for key in sorted(set(before) | set(after), key=lambda k: (k[0].casefold(), k[1].casefold(), k)):
        b, a = before.get(key), after.get(key)
        if b is not None and a is not None and b == a and not show_unchanged:
            continue
        change = _signed(a - b) if b is not None and a is not None else None
        rows.append({"tool": key[0], "metric": key[1], "before": b, "after": a, "change": change})
    return rows[:MAX_TEST_ROWS], max(0, len(rows) - MAX_TEST_ROWS)


def part_html(part: str, title: str, body, *, t) -> str:
    body = Markup(body) if body else Markup('<p class="placeholder">') + escape(t("No change.")) + Markup("</p>")
    return str(Markup('<section class="changes" data-changes="{}"><h3>{}</h3>').format(part, title) + body
               + Markup("</section>"))


def summary_line(changed: list[bool], *, base, this, t) -> str | None:
    if any(changed):
        return None
    return t("No changes between version {base} and version {this} in the selected parts.", base=base, this=this)


# the block

class ChangesSinceBlock(BaseBlockRenderer):
    type_id = "changes_since"
    title = "Changes since an earlier version"
    contract_version = 1
    description = "What changed in the card, objectives, tests and controls since an earlier version."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "compare_to": {"enum": ["previous"], "title": "Compare with",
                           "description": "The version before, or the version chosen when the report is generated.",
                           "x-aisc-enum-labels": {"previous": "The version before"}},
            "sections": {"type": "array", "uniqueItems": True, "items": {"enum": SECTIONS}, "title": "Parts",
                         "description": "Which parts to compare.", "x-aisc-enum-labels": dict(SECTION_LABELS)},
            "show_unchanged": {"type": "boolean", "title": "Show unchanged items",
                               "description": "Also lists what stayed the same.", "x-aisc-more": True},
        },
    }
    default_options = {"compare_to": "previous", "sections": list(SECTIONS), "show_unchanged": False}
    reads = ("platform", "qualification", "control_objectives", "engine", "controls")
    choice_options = ()

    def load(self, ctx, options):
        # the report's selection names the version to compare with; the block option is the fallback
        compare_to = getattr(selection_of(ctx), "compare_to", None) or options["compare_to"]
        # two versions are compared whole: the report's period and other versions do not apply here
        ctx = dataclasses.replace(ctx, report=dataclasses.replace(ctx.report, selection=EMPTY))
        if compare_to == "previous":
            base_row = previous_version(ctx.data.platform.older_versions())
            if base_row is None:
                return {"none": True}
            compare_to = base_row["pid"]
        try:
            base = ctx.data.for_version(compare_to)
        except (NotInProject, ValueError):
            return {"bad": True}
        base_ctx = dataclasses.replace(ctx, system=base.system, data=base, newer_versions=())
        wanted = [s for s in SECTIONS if s in options["sections"]]
        sides = {}
        for name, c in (("base", base_ctx), ("this", ctx)):
            sides[name] = {part: getattr(self, f"_read_{part}")(c) for part in wanted}
        return {"base_number": base.system_number, "sides": sides, "parts": wanted}

    # readers: each returns plain data for one side

    def _read_card(self, c):
        q = c.data.qualification
        card = q.card()
        return {"system": dict(c.system), "card": card,
                "components": {(x["name"], x["component_type"]) for x in q.components()} if card else set(),
                "risks": {r["risk"] for r in q.risks()} if card else set()}

    def _read_objectives(self, c):
        co = c.data.control_objectives
        if co.assessment() is None:
            return None
        rows = co.mappings()
        ids = co.objective_ids()
        risks = {}
        for r in rows:
            risks.setdefault(r["risk_id"], {"label": r.get("short_label") or r["risk_id"],
                                            "rating": r["rating"]})
        coverage = coverage_for(c, ids, c.report.coverage_links)
        return {"ids": ids, "risks": risks, "coverage": {oid: cov.status for oid, cov in coverage.items()}}

    def _read_tests(self, c):
        view = load_runs(c, statuses=["Done"])
        counts: dict[str, int] = {}
        latest: dict[str, object] = {}
        for ev in view.evaluations:
            seen = set()
            for rv in ev.runs:
                name = rv.tool.get("display_name") or rv.tool.get("name") or ""
                if name and name not in seen:
                    counts[name] = counts.get(name, 0) + 1
                    seen.add(name)
                latest[name] = rv
        means: dict[tuple[str, str], float] = {}
        for name, rv in latest.items():
            groups: dict[str, list[float]] = {}
            for m in rv.run.measurements:
                if m.get("score") is not None:
                    groups.setdefault(m.get("metric") or m.get("name"), []).append(float(m["score"]))
            for metric, scores in groups.items():
                means[(name, metric)] = sum(scores) / len(scores)
        return {"counts": counts, "means": means}

    def _read_controls(self, c):
        view = load_answers(c)
        return {ca.checklist["id"]: {"title": ca.checklist["title"], "answered": ca.answered, "total": ca.total,
                                     "mean": ca.mean} for ca in view.checklists if ca.answered}

    # rendering

    def render(self, data, options, ctx):
        t = ctx.t
        if data.get("none"):
            return empty_result(t("No earlier version to compare with."))
        if data.get("bad"):
            return BlockResult(html='<div class="error-box"><p>' + str(escape(
                t("The version to compare with is not an earlier version of this project."))) + "</p></div>",
                status="error", notices=[])
        b, s = data["base_number"], ctx.system["number"]
        show = bool(options["show_unchanged"])
        parts_html = []
        changed = []
        for part in data["parts"]:
            body, has_change = getattr(self, f"_diff_{part}")(data["sides"]["base"][part], data["sides"]["this"][part],
                                                              b, s, show, ctx)
            changed.append(has_change)
            parts_html.append(part_html(part, t(SECTION_LABELS[part]), body if (has_change or show) else "", t=t))
        head = Markup('<p class="changes-intro">') + escape(
            t("This section compares version {this} (this report) with version {base}.", this=s, base=b)) + \
            Markup("</p>")
        line = summary_line(changed, base=b, this=s, t=t)
        if line:
            head += Markup('<p class="placeholder">') + escape(line) + Markup("</p>")
        return BlockResult(html=str(head + Markup("".join(parts_html))), status="ok", notices=[])

    def _table(self, header, rows, ctx) -> Markup:
        out = Markup("<table><thead><tr>") + Markup("").join(Markup("<th>{}</th>").format(h) for h in header) \
            + Markup("</tr></thead><tbody>")
        for r in rows:
            out += Markup("<tr>") + Markup("").join(Markup("<td>{}</td>").format(c) for c in r) + Markup("</tr>")
        return out + Markup("</tbody></table>")

    def _versions_header(self, t, b, s):
        return [t("Version {number}", number=b), t("Version {number}", number=s)]

    def _diff_card(self, before, after, b, s, show, ctx):
        t = ctx.t
        rows, changed = [], False
        for key, label in VERSION_FIELDS:
            x, y = before["system"].get(key), after["system"].get(key)
            if x != y:
                changed = True
            if x != y or show:
                rows.append((t(label), cut(x), cut(y)))
        cb, ca = before["card"], after["card"]
        if cb is None or ca is None:
            if (cb is None) != (ca is None):
                changed = True
            if cb is None and ca is None:
                pass
            else:
                rows.append((t("AI card"), cut(cb.get("system_name")) if cb else t("No AI card for version {number}.", number=b),
                             cut(ca.get("system_name")) if ca else t("No AI card for version {number}.", number=s)))
        else:
            for key, label in CARD_FIELDS:
                x, y = cb.get(key), ca.get(key)
                if x != y:
                    changed = True
                if x != y or show:
                    rows.append((t(label), cut(x), cut(y)))
            for key, label in TAG_FIELDS:
                x, y = set(cb.get(key) or []) - {""}, set(ca.get(key) or []) - {""}
                if x != y:
                    changed = True
                if x != y or show:
                    rows.append((t(label), tag_text(x, key, ctx.data.vocab), tag_text(y, key, ctx.data.vocab)))
        html = self._table([t("Field")] + self._versions_header(t, b, s), rows, ctx) if rows else Markup("")
        lists = []
        for title, x, y, fmt in ((t("Components"), before["components"], after["components"],
                                  lambda c: f"{c[0]} ({c[1]})"),
                                 (t("Risks of the AI card"), before["risks"], after["risks"], str)):
            added, removed = sorted(y - x), sorted(x - y)
            if added or removed:
                changed = True
            items = [t("Added: {item}", item=cut(fmt(v))) for v in added] + \
                    [t("Removed: {item}", item=cut(fmt(v))) for v in removed]
            if show:
                items += [t("Unchanged: {item}", item=cut(fmt(v))) for v in sorted(x & y)]
            if items:
                lists.append(Markup("<h4>{}</h4><ul>").format(title)
                             + Markup("").join(Markup("<li>{}</li>").format(i) for i in items) + Markup("</ul>"))
        return html + Markup("").join(lists), changed

    def _diff_objectives(self, before, after, b, s, show, ctx):
        t = ctx.t
        if before is None or after is None:
            if before is None and after is None:
                return Markup(""), False
            n = b if before is None else s
            return Markup("<p>") + escape(t("No control objectives for version {number}.", number=n)) + \
                Markup("</p>"), True
        labels = ctx.data.objectives
        changes, same = [], []
        for oid in sorted(set(after["ids"]) - set(before["ids"]), key=objective_order):
            changes.append(t("Objective added: {id} {label}", id=oid, label=labels.get(oid, {}).get("label", "")))
        for oid in sorted(set(before["ids"]) - set(after["ids"]), key=objective_order):
            changes.append(t("Objective removed: {id} {label}", id=oid, label=labels.get(oid, {}).get("label", "")))
        for rid in sorted(set(after["risks"]) - set(before["risks"])):
            changes.append(t("Risk added: {id} {label}", id=rid, label=after["risks"][rid]["label"]))
        for rid in sorted(set(before["risks"]) - set(after["risks"])):
            changes.append(t("Risk removed: {id} {label}", id=rid, label=before["risks"][rid]["label"]))

        def rated(v):
            return t("not rated") if v is None else t("rating {rating}", rating=v)

        for rid in sorted(set(before["risks"]) & set(after["risks"])):
            x, y = before["risks"][rid]["rating"], after["risks"][rid]["rating"]
            label = after["risks"][rid]["label"]
            if x != y and x is not None and y is not None:
                changes.append(t("{label}: rating {before} to {after}", label=label, before=x, after=y))
            elif x != y:
                changes.append(t("{label}: {before} to {after}", label=label, before=rated(x), after=rated(y)))
            else:
                same.append(t("{label}: {value}", label=label, value=rated(y)))
        for oid in sorted(set(before["ids"]) & set(after["ids"]), key=objective_order):
            x, y = before["coverage"].get(oid), after["coverage"].get(oid)
            if x != y:
                changes.append(t("Coverage of {id}: {before} to {after}", id=oid, before=t(x), after=t(y)))
            else:
                same.append(t("Coverage of {id}: {status}", id=oid, status=t(y)))
        items = changes + ([t("Unchanged: {item}", item=i) for i in same] if show else [])
        if not items:
            return Markup(""), False
        return Markup("<ul>") + Markup("").join(Markup("<li>{}</li>").format(i) for i in items) + \
            Markup("</ul>"), bool(changes)

    def _diff_tests(self, before, after, b, s, show, ctx):
        t = ctx.t
        count_rows, changed = [], False
        for tool in sorted(set(before["counts"]) | set(after["counts"]), key=str.casefold):
            x, y = before["counts"].get(tool, 0), after["counts"].get(tool, 0)
            if x != y:
                changed = True
            if x != y or show:
                count_rows.append((tool, str(x), str(y)))
        rows, more = compare_metrics(before["means"], after["means"], show_unchanged=show)
        # every pair, not only the rows shown: a change past the 200th row is still a change
        if any(before["means"].get(k) != after["means"].get(k) for k in set(before["means"]) | set(after["means"])):
            changed = True

        def val(v):
            return ctx.number(f"{v:g}") if v is not None else ""

        metric_rows = []
        for r in rows:
            if r["change"] is not None:
                change = ctx.number(r["change"])
            else:
                change = t("only in version {number}", number=s if r["before"] is None else b)
            metric_rows.append((r["tool"], r["metric"], val(r["before"]), val(r["after"]), change))
        html = Markup("")
        if count_rows:
            html += Markup("<h4>{}</h4>").format(t("Done evaluations per tool")) + \
                self._table([t("Tool")] + self._versions_header(t, b, s), count_rows, ctx)
        if metric_rows:
            html += Markup("<h4>{}</h4>").format(t("Mean score of each metric in the tool's latest Done run")) + \
                self._table([t("Tool"), t("Metric")] + self._versions_header(t, b, s) + [t("Change")], metric_rows,
                            ctx)
        if more:
            html += Markup('<p class="more">{}</p>').format(t("and {count} more", count=more))
        return html, changed

    def _diff_controls(self, before, after, b, s, show, ctx):
        t = ctx.t
        rows, changed = [], False

        def side(v):
            if v is None:
                return ""
            text = t("answered {answered} of {total}", answered=v["answered"], total=v["total"])
            if v["mean"] is not None:
                text += ", " + t("mean score {mean}", mean=ctx.number(v["mean"]))
            return text

        for cid in sorted(set(before) | set(after), key=lambda k: ((before.get(k) or after.get(k))["title"] or "", k)):
            x, y = before.get(cid), after.get(cid)
            if x is None or y is None:
                changed = True
                change = t("only in version {number}", number=s if x is None else b)
            else:
                same = (x["answered"], x["total"], x["mean"]) == (y["answered"], y["total"], y["mean"])
                if same and not show:
                    continue
                if not same:
                    changed = True
                change = _signed(y["mean"] - x["mean"]) if x["mean"] is not None and y["mean"] is not None else ""
                change = ctx.number(change)
            title = (y or x)["title"]
            rows.append((title, side(x), side(y), change))
        if not rows:
            return Markup(""), False
        return self._table([t("Checklist")] + self._versions_header(t, b, s) + [t("Change of the mean score")],
                           rows, ctx), changed
