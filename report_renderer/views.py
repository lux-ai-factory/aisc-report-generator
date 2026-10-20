"""The pinned version's runs and answers, shared by the blocks and the coverage rule."""
from __future__ import annotations

from dataclasses import dataclass, field

from aisc_report_plugin_interface import ToolRun, normalise_tool_name, tool_keys
from aisc_report_plugin_interface.i18n import fill

from .data.engine import TARGET_INPUT
from .selection import Selection


def selection_of(ctx):
    """The report's data selection; None outside a report."""
    return getattr(getattr(ctx, "report", None), "selection", None)


def version_suffix(ctx, version_number) -> str:
    """" (version N)" for a run of another version than the report's, " (no version)" for none."""
    if version_number is None:
        return " (no version)"
    return "" if version_number == ctx.system.get("number") else f" (version {version_number})"


@dataclass
class RunView:
    tool: dict
    components: list
    status: str
    run: ToolRun
    artifacts: list


@dataclass
class EvaluationView:
    evaluation: dict
    runs: list[RunView]
    unmatched: list[dict]
    unmatched_count: int


@dataclass
class RunsView:
    evaluations: list[EvaluationView]
    unversioned: int


def _tool_of(r: dict) -> dict:
    if r.get("plugin_name") or r.get("display_name"):
        return {"display_name": r.get("display_name") or r.get("plugin_name"), "name": r.get("plugin_name"),
                "package_name": r.get("package_name"), "version": r.get("version")}
    return {"display_name": r["name"], "name": r["name"], "package_name": None, "version": None}


def _keys(tool: dict) -> set[str]:
    return tool_keys(tool.get("display_name"), tool.get("name"), tool.get("package_name"))


def evaluation_names(ctx) -> dict[str, tuple[int, str]]:
    """pid -> (k, "Evaluation {k}: {tools}"), k counted over every evaluation of the version
    (any status, ordered by created_at then id), whatever a block's filters."""
    t = getattr(ctx, "t", None) or (lambda msgid, **p: fill(msgid, p))
    engine = ctx.data.engine
    sel = selection_of(ctx)
    # numbered over the runs the selection can show, whatever its period, so numbers stay put
    whole = Selection(other_versions=bool(sel and sel.other_versions))
    evals = engine.evaluations(selection=whole)
    runs = engine.runs(evaluation_ids=[e["id"] for e in evals], selection=whole)
    out: dict[str, tuple[int, str]] = {}
    for k, e in enumerate(evals, start=1):
        tools: list[str] = []
        for r in runs:
            if r["evaluation_id"] != e["id"]:
                continue
            name = _tool_of(r)["display_name"]
            if name and name not in tools:
                tools.append(name)
        if not tools:
            label = t("Evaluation {number}", number=k)
        else:
            shown = ", ".join(tools[:3])
            if len(tools) > 3:
                shown = t("{tools}, +{count} more", tools=shown, count=len(tools) - 3)
            label = t("Evaluation {number}: {tools}", number=k, tools=shown)
        out[e["pid"]] = (k, label + version_suffix(ctx, e.get("version_number")))
    return out


def _pair_keys(metrics) -> set[tuple[str, str]] | None:
    if metrics in (None, "all"):
        return None
    return {(normalise_tool_name(m.get("tool", "")), str(m.get("metric", ""))) for m in metrics}


def metric_choices(ctx) -> list[dict]:
    """Every distinct (tool display name, metric) of the project's measurements, of any status and any
    version, so that a layout naming a metric holds for every version. One query returns the distinct
    pairs (data.engine.metric_pairs), named as load_runs names them."""
    pairs = {(r["tool"], r["metric"]) for r in ctx.data.engine.metric_pairs()}
    ordered = sorted(pairs, key=lambda p: (p[0].casefold(), p[1].casefold(), p[0], p[1]))
    return [{"value": {"tool": tool, "metric": metric}, "label": f"{tool}: {metric}"} for tool, metric in ordered]


def kind_label(component_kind) -> str:
    """"training_data" -> "Training data"."""
    words = str(component_kind or "component").replace("_", " ").replace("-", " ").strip()
    return words[:1].upper() + words[1:]


def target_label(t) -> str:
    """"System: Example Assistant", or "Scoring model (Model)"."""
    if t.get("kind") == "system":
        return f"System: {t['label']}"
    return f"{t['label']} ({kind_label(t.get('component_kind'))})"


def target_choices(ctx) -> list[dict]:
    """Every target of the project, the system first: a layout naming a target holds for every version."""
    return [{"value": t["key"], "label": target_label(t)} for t in ctx.data.engine.targets()]


def run_target(inputs: list[dict], by_component: dict, latest, card_version):
    """What a run assessed, from its input named `target`: the platform's
    target whose engine mirror is that input's component; "not a target" when the component is no
    mirror; None for a run made before targets."""
    given = next((i for i in inputs if i.get("input_name") == TARGET_INPUT), None)
    if given is None:
        return None
    t = by_component.get(given.get("component_pid"))
    if t is None:
        return {"key": None, "kind": None, "component_kind": None, "label": given["name"],
                "card_version": card_version, "status": "not a target"}
    stale = (t["kind"] == "component" and t.get("last_card_number") is not None and latest is not None
             and t["last_card_number"] < latest)
    return {"key": t["key"], "kind": t["kind"], "component_kind": t.get("component_kind"), "label": t["label"],
            "card_version": card_version, "status": "stale" if stale else "current"}


def _target_wanted(target, wanted: set[str] | None) -> bool:
    if wanted is None:
        return True
    return bool(target and target.get("key") and ({target["key"], target["label"]} & wanted))


def load_runs(ctx, *, statuses, tools=None, metrics="all", names=None, targets=None) -> RunsView:
    engine = ctx.data.engine
    sel = selection_of(ctx)
    evals = engine.evaluations(statuses=list(statuses) if statuses is not None else None, selection=sel)
    ids = [e["id"] for e in evals]
    runs = engine.runs(evaluation_ids=ids, selection=sel)
    run_ids = [r["id"] for r in runs]
    inputs = engine.inputs(run_ids=run_ids, selection=sel)
    observations = engine.observations(evaluation_ids=ids, selection=sel)
    measurements = engine.measurements(observation_ids=[o["id"] for o in observations], selection=sel)
    artifacts = engine.artifacts(run_ids=run_ids, selection=sel)
    has_target = any(i.get("input_name") == TARGET_INPUT for i in inputs)
    by_component = {t["engine_component"]: t for t in engine.targets() if t.get("engine_component")} \
        if has_target else {}
    latest = engine.latest_card_number() if has_target else None
    wanted_targets = None if targets in (None, "all") else {str(x) for x in targets}

    by_obs: dict[int, list] = {}
    for m in measurements:
        by_obs.setdefault(m["observation_id"], []).append(
            {k: m.get(k) for k in ("name", "metric", "score", "unit", "uncertainty", "dimensions", "direction",
                                   "description", "error")})
    pairs = _pair_keys(metrics)
    wanted = None if tools in (None, "all") else {normalise_tool_name(t) for t in tools}

    views = []
    for e in evals:
        e_runs = [r for r in runs if r["evaluation_id"] == e["id"]]
        e_obs = [o for o in observations if o["evaluation_id"] == e["id"]]
        taken: set[int] = set()
        matched: dict[int, list] = {}
        for r in e_runs:
            if r.get("plugin_name"):
                tag = f"{r['package_name']}::{r['plugin_name']} (v{r['version']})"
                matched[r["id"]] = [o for o in e_obs if o["tool"] == tag]
            else:
                matched[r["id"]] = []
        if len(e_runs) == 1 and not matched[e_runs[0]["id"]]:
            matched[e_runs[0]["id"]] = list(e_obs)
        for obs in matched.values():
            taken.update(o["id"] for o in obs)
        unmatched_obs = [o for o in e_obs if o["id"] not in taken]

        run_views = []
        for r in e_runs:
            tool = _tool_of(r)
            if wanted is not None and not (wanted & _keys(tool)):
                continue
            r_inputs = [i for i in inputs if i["evaluation_plugin_id"] == r["id"]]
            target = run_target(r_inputs, by_component, latest, e.get("version_number"))
            if not _target_wanted(target, wanted_targets):
                continue
            comps = [{"name": i["name"], "component_type": i["component_type"]} for i in r_inputs]
            arts = [{"name": a["name"], "file_size": a["file_size"]} for a in artifacts
                    if a["evaluation_plugin_id"] == r["id"]]
            obs = matched[r["id"]]
            ms = [m for o in obs for m in by_obs.get(o["id"], [])]
            if pairs is not None:
                tool_key = normalise_tool_name(tool.get("display_name") or tool.get("name") or "")
                ms = [m for m in ms if (tool_key, str(m.get("metric") or m.get("name"))) in pairs]
            evaluation = {"pid": e["pid"], "status": e["status"], "created_at": e["created_at"].isoformat()}
            if names is not None and e["pid"] in names:
                evaluation["number"], evaluation["name"] = names[e["pid"]]
            run = ToolRun(
                evaluation=evaluation,
                evaluation_plugin={"pid": r["pid"], "name": r["name"], "status": r["status"],
                                   "plugin_config_id": r.get("plugin_config_id")},
                tool=tool, components=comps, observations=[{"id": o["id"], "tool": o["tool"]} for o in obs],
                measurements=ms, artifacts=arts, target=target)
            run_views.append(RunView(tool=tool, components=comps, status=r["status"], run=run, artifacts=arts))
        if (wanted is not None or wanted_targets is not None) and not run_views:
            continue
        views.append(EvaluationView(evaluation=e, runs=run_views,
                                    unmatched=[m for o in unmatched_obs for m in by_obs.get(o["id"], [])],
                                    unmatched_count=len(unmatched_obs)))
    # with other versions on, the unversioned runs are shown, so none is left out
    unversioned = 0 if (sel and sel.other_versions) else engine.unversioned_count()
    return RunsView(evaluations=views, unversioned=unversioned)


@dataclass
class ChecklistAnswers:
    checklist: dict
    submission: dict
    rows: list[dict]              # {question, article, answer, score, answered}
    other_version_answers: int
    answered: int
    total: int
    mean: float | None


@dataclass
class AnswersView:
    checklists: list[ChecklistAnswers] = field(default_factory=list)
    missing_db: bool = False
    unknown_checklists: list[str] = field(default_factory=list)


def answer_sheet(status: str, questions: list[dict], answers: list[dict]) -> list[tuple[dict, dict | None]]:
    """The questions a submission shows, in order, each with its answer or None: the controls app's rule
    (apps/controls/src/lib/answerSheet.ts).

    A draft follows the template: today's questions. A closed submission is frozen: each question it answered
    is shown as it was when it was closed (the wording its answer keeps), an answer to a question removed
    since included. The template's questions it left unanswered have no answer to keep their wording, so they
    are shown as they are now. `questions` are the checklist's today, `answers` the submission's."""
    by_id = {q["id"]: q for q in questions}
    if status != "Closed":
        mine = {a["question_id"]: a for a in answers if a["question_id"] in by_id}
        return [(q, mine.get(q["id"])) for q in questions]
    answered = []
    for a in answers:
        now = by_id.get(a["question_id"])
        if a["question_text"] is None:
            # An answer closed before the wording was kept takes today's, the best known.
            if now is not None:
                answered.append((now, a))
            continue
        position = a["question_order"] if a["question_order"] is not None else (now or {}).get("position", 0)
        answered.append(({"text": a["question_text"], "article": a["question_article"], "position": position}, a))
    asked = {a["question_id"] for a in answers}
    unanswered = [(q, None) for q in questions if q["id"] not in asked]
    # sorted is stable: at the same place, the answered question comes first
    return sorted(answered + unanswered, key=lambda row: row[0]["position"])


def load_answers(ctx, *, checklists="all", include_archived=False) -> AnswersView:
    controls = ctx.data.controls
    all_lists = controls.checklists()
    if all_lists is None:
        return AnswersView(missing_db=True)
    known = {c["id"] for c in all_lists}
    unknown: list[str] = []
    if checklists not in (None, "all"):
        unknown = [c for c in checklists if c not in known]
        chosen = set(checklists)
        all_lists = [c for c in all_lists if c["id"] in chosen]
    subs = controls.submissions_with_answers(include_archived=include_archived) or []
    latest: dict[str, dict] = {}
    for s in subs:
        latest.setdefault(s["checklist_id"], s)
    shown = [c for c in all_lists if c["id"] in latest]
    questions = controls.questions(checklist_ids=[c["id"] for c in shown])
    answers = controls.answers(submission_ids=[latest[c["id"]]["id"] for c in shown])
    pinned = ctx.data.system_id
    out = []
    for c in shown:
        sub = latest[c["id"]]
        given = [a for a in answers if a["submission_id"] == sub["id"]]
        others = sum(1 for a in given if a["system_version_pid"] != pinned)
        rows = []
        for q, a in answer_sheet(sub["status"], [q for q in questions if q["checklist_id"] == c["id"]], given):
            if a is not None and a["system_version_pid"] != pinned:
                a = None
            rows.append({"question": q["text"], "article": q["article"] or "",
                         "answer": a["answer"] if a else None, "score": a["score"] if a else None,
                         "answered": a is not None})
        scores = [r["score"] for r in rows if r["answered"] and r["score"] is not None]
        out.append(ChecklistAnswers(checklist=c, submission=sub, rows=rows, other_version_answers=others,
                                    answered=sum(1 for r in rows if r["answered"]), total=len(rows),
                                    mean=round(sum(scores) / len(scores), 1) if scores else None))
    return AnswersView(checklists=out, unknown_checklists=unknown)
