"""LangBiTe (Mijke)'s conversations compared: how often a person is sent where the baseline, or another person, is.

The same rules as the results dashboard's two datasets ("Mijke conversations compared"), on a run's Conversation
results: two conversations of the same run that asked the same question (scenario, register, language, repetition)
agree when they ended with the same set of organisations, or both with none. Nothing is stored or judged again:
the outcome and the organisations are the plugin's.

Pure: the block reads the runs and draws (blocks/conversation_comparison.py)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

CONVERSATION_METRIC = "Conversation"
BASELINE = "BASELINE"
SEPARATOR = "|"
REGISTERS = ("basic", "advanced", "broken")
#: the status questions name a person by a whole sentence: too long for a chart
SHORT_NAMES = {"I am a refugee": "refugee", "I am an immigrant": "immigrant",
               "I moved to the Netherlands and I am now a Dutch citizen": "naturalised citizen",
               "My parents moved to the Netherlands, I was born here": "second generation",
               "I was born in the Netherlands": "born in NL"}


@dataclass
class Compared:
    """Each share is from 0 to 1. Keys of by_*: what the chart's axes name; values: {model: share}."""
    models: list[str] = field(default_factory=list)
    overall: dict = field(default_factory=dict)       # {model: (share, conversations)}
    by_register: dict = field(default_factory=dict)   # {"EN basic": {model: share}}
    by_category: dict = field(default_factory=dict)   # {"Age": {model: share}}
    by_community: dict = field(default_factory=dict)  # {("Age", "70"): {model: share}}
    widest: dict = field(default_factory=dict)        # {(model, category): (pair, share, pairs)}
    repeat: tuple | None = None                       # (share, pairs): the same question asked in two runs


def is_conversation(measurement: dict) -> bool:
    return (measurement.get("name") or measurement.get("metric")) == CONVERSATION_METRIC


def without_conversations(measurements) -> tuple[list, int]:
    """The other results, and how many conversation results were taken out."""
    kept = [m for m in measurements if not is_conversation(m)]
    return kept, len(measurements) - len(kept)


def _orgs(d: dict) -> frozenset:
    return frozenset(o.strip().lower() for o in str(d.get("organisations") or "").split(SEPARATOR) if o.strip())


def _question(d: dict) -> tuple:
    return d.get("scenario"), d.get("register"), d.get("language"), d.get("repetition")


def _share(values) -> float:
    return sum(values) / len(values)


def _register_order(label: str) -> tuple:
    language, _, register = label.partition(" ")
    place = REGISTERS.index(register) if register in REGISTERS else len(REGISTERS)
    return language, place, register


def _slot(d: dict) -> tuple:
    """A conversation's slot as a sort key: numbers in order (no slot counts as 0), then text, then none."""
    slot = d.get("slot", 0)
    if isinstance(slot, (int, float)):
        return 0, slot, ""
    return (1, 0, str(slot)) if slot is not None else (2, 0, "")


def compare(runs) -> Compared:
    """runs: (model, measurements) per plugin run."""
    overall, registers, categories, communities = (defaultdict(list) for _ in range(4))
    pairs, order = defaultdict(list), {}
    baselines_of = defaultdict(list)                  # (model, category): the baselines of each run
    for model, measurements in runs:
        rows = [m.get("dimensions") or {} for m in measurements if is_conversation(m)]
        baseline = {_question(d): _orgs(d) for d in rows if d.get("category") == BASELINE}
        people = [d for d in rows if d.get("category") != BASELINE]
        names = {(d.get("category"), d.get("slot")): d.get("community") for d in people if d.get("language") == "en"}

        def name_of(d):
            name = names.get((d.get("category"), d.get("slot")), d.get("community"))
            return SHORT_NAMES.get(name, name)

        for category in {d.get("category") for d in people}:
            baselines_of[(model, category)].append(baseline)
        for d in people:
            question = _question(d)
            if question not in baseline:
                continue
            same = _orgs(d) == baseline[question]
            category = str(d.get("category")).capitalize()
            overall[model].append(same)
            registers[(f'{str(d.get("language")).upper()} {d.get("register")}', model)].append(same)
            categories[(category, model)].append(same)
            communities[((category, name_of(d)), _slot(d), model)].append(same)
        by_question = defaultdict(list)
        for d in people:
            by_question[(d.get("category"),) + _question(d)].append(d)
        for group in by_question.values():
            for x, y in combinations(sorted(group, key=_slot), 2):
                key = (model, str(x.get("category")).capitalize(), name_of(x), name_of(y))
                pairs[key].append(_orgs(x) == _orgs(y))
                order[key] = (_slot(x), _slot(y))
    out = Compared()
    out.models = sorted(overall)
    out.overall = {m: (_share(v), len(v)) for m, v in overall.items()}
    for (label, model), v in sorted(registers.items(), key=lambda kv: _register_order(kv[0][0])):
        out.by_register.setdefault(label, {})[model] = _share(v)
    for (label, model), v in sorted(categories.items()):
        out.by_category.setdefault(label, {})[model] = _share(v)
    for (label, _place, model), v in sorted(communities.items(), key=lambda kv: (kv[0][0][0], kv[0][1])):
        out.by_community.setdefault(label, {})[model] = _share(v)
    for key in sorted(pairs, key=lambda k: (k[0], k[1], _share(pairs[k]), order[k])):
        model, category, a, b = key
        out.widest.setdefault((model, category), (f"{a} vs {b}", _share(pairs[key]), len(pairs[key])))
    repeats = [one[q] == other[q] for baselines in baselines_of.values() for one, other in combinations(baselines, 2)
               for q in one.keys() & other.keys()]
    out.repeat = (_share(repeats), len(repeats)) if repeats else None
    return out
