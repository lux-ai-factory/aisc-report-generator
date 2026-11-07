"""LangBiTe (Mijke)'s conversations compared: how often a person is sent where the baseline is.

The same rules as the results dashboard's two datasets ("Mijke conversations compared"), on a run's Conversation
results: two conversations of the same run that asked the same question (scenario, register, language, repetition)
agree when they ended with the same set of organisations, or both with none. Nothing is stored or judged again:
the outcome and the organisations are the plugin's.

Pure: the block reads the runs and draws (blocks/conversation_comparison.py)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

CONVERSATION_METRIC = "Conversation"
BASELINE = "BASELINE"
SEPARATOR = "|"


@dataclass
class Compared:
    """overall: {model: (share, conversations)}, the share from 0 to 1."""
    overall: dict = field(default_factory=dict)


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


def compare(runs) -> Compared:
    """runs: (model, measurements) per plugin run. How often a person ended where the baseline of the same question,
    in the same run, ended."""
    overall = defaultdict(list)
    for model, measurements in runs:
        rows = [m.get("dimensions") or {} for m in measurements if is_conversation(m)]
        baseline = {_question(d): _orgs(d) for d in rows if d.get("category") == BASELINE}
        for d in rows:
            question = _question(d)
            if d.get("category") != BASELINE and question in baseline:
                overall[model].append(_orgs(d) == baseline[question])
    return Compared(overall={m: (sum(v) / len(v), len(v)) for m, v in overall.items()})
