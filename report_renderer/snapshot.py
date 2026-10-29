"""The layout snapshot the composer sends, its schema and its checks.

Version 3 is the only one taken (a snapshot that names no version is read as version 3); every key past
the required ones is optional."""
from __future__ import annotations

import copy
import hashlib
import json

from jsonschema import Draft202012Validator

from . import style as _style

UUID_PATTERN = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["project_id", "system_id", "layout", "blocks", "mode"],
    "properties": {
        "project_id": {"type": "string", "pattern": UUID_PATTERN},
        "system_id": {"type": "string", "pattern": UUID_PATTERN},
        "layout": {
            "type": "object",
            "required": ["id", "name", "revision"],
            "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "revision": {"type": "integer"}},
        },
        "blocks": {
            "type": "array",
            "maxItems": 50,
            "items": {
                "type": "object",
                "required": ["instance_id", "block_type", "options"],
                "properties": {
                    "instance_id": {"type": "string", "pattern": UUID_PATTERN},
                    "block_type": {"type": "string", "minLength": 1},
                    "options": {"type": "object"},
                },
            },
        },
        "mode": {"enum": ["preview", "pdf", "docx"]},
        "requested_by": {"type": "string"},
        "snapshot_version": {"type": "integer", "enum": [3]},
        "document": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {"type": ["string", "null"], "pattern": UUID_PATTERN},
                "toc": {"enum": ["on", "off"]},
                "numbering": {"type": "boolean"},
                # the newest entry of the project's ledger when the report was made, printed on it
                "ledger_anchor": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["seq", "entry_sha256"],
                    "properties": {
                        "seq": {"type": "integer", "minimum": 1},
                        "entry_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                },
            },
        },
        "coverage_links": {
            "type": "array",
            "maxItems": 200,
            "items": {
                "type": "object",
                "required": ["objective_id"],
                "properties": {
                    "objective_id": {"type": "string", "minLength": 1},
                    "tests": {"type": "array", "items": {"type": "string"}},
                    "checklists": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        # the data the report covers; absent means the anchor version alone
        "selection": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "period_from": {"type": ["string", "null"], "format": "date-time"},
                "period_to": {"type": ["string", "null"], "format": "date-time"},
                "other_versions": {"type": "boolean"},
                "compare_to": {"type": ["string", "null"], "pattern": UUID_PATTERN},
            },
        },
        # the template's look (font, size, colours, logo); absent means the platform look
        "style": _style.SCHEMA,
        # what each plugin declares (get_metric_visualizations), per plugin configuration id (declared.py)
        "declared_charts": {
            "type": "object",
            "maxProperties": 200,
            "additionalProperties": {"type": "array", "maxItems": 30, "items": {"type": "object"}},
        },
    },
}

_VALIDATOR = Draft202012Validator(SCHEMA)


def _instance_id(snapshot, path: list) -> str | None:
    if len(path) >= 2 and path[0] == "blocks" and isinstance(path[1], int):
        blocks = snapshot.get("blocks") if isinstance(snapshot, dict) else None
        if isinstance(blocks, list) and path[1] < len(blocks) and isinstance(blocks[path[1]], dict):
            iid = blocks[path[1]].get("instance_id")
            return _printable(iid) if isinstance(iid, str) else None
    return None


def _message(err) -> str:
    if err.validator == "required":
        return "is required"
    if err.validator == "type":
        return f"must be of type {err.validator_value}"
    if err.validator == "pattern":
        return "must be a UUID" if err.validator_value == UUID_PATTERN else "is not valid"
    if err.validator == "enum":
        return "must be one of " + ", ".join(str(v) for v in err.validator_value)
    if err.validator == "maxItems":
        return f"must have at most {err.validator_value} items"
    if err.validator == "minLength":
        return "must not be empty"
    if err.validator == "maxLength":
        return f"must be at most {err.validator_value} characters"
    return err.message[:200]


def _has_lone_surrogate(text: str) -> bool:
    return any("\ud800" <= ch <= "\udfff" for ch in text)


def _printable(part) -> str:
    return str(part).encode("utf-8", "backslashreplace").decode("utf-8")


def _surrogate_problems(snapshot) -> list[dict]:
    """A lone surrogate (valid JSON as an escape, not text) in any key or string is
    refused, since nothing can encode it. The pointer shows it as a backslash escape."""
    problems: list[dict] = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and _has_lone_surrogate(k):
                    problems.append(_surrogate_problem(snapshot, path + [k]))
                walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [i])
        elif isinstance(node, str) and _has_lone_surrogate(node):
            problems.append(_surrogate_problem(snapshot, path))

    walk(snapshot, [])
    return problems


SURROGATE_MESSAGE = "holds a lone surrogate"


def _surrogate_problem(snapshot, path) -> dict:
    return {"instance_id": _instance_id(snapshot, path), "code": "invalid_snapshot",
            "pointer": "".join("/" + _printable(p) for p in path),
            "message": SURROGATE_MESSAGE}


def _content_problems(s) -> list[dict]:
    """What the schema can't say: the logo is what its mime says, and the period is a date-time with a
    time zone (its "format" is not checked by the validator)."""
    from datetime import datetime

    from report_renderer.style import logo_problem

    out = []
    if isinstance(s, dict) and isinstance(s.get("style"), dict):
        why = logo_problem(s["style"])
        if why:
            out.append({"instance_id": None, "code": "invalid_snapshot", "pointer": "/style/logo/data_base64",
                        "message": why})
    selection = s.get("selection") if isinstance(s, dict) else None
    if isinstance(selection, dict):
        for key in ("period_from", "period_to"):
            value = selection.get(key)
            if not isinstance(value, str):
                continue
            try:
                ok = datetime.fromisoformat(value).tzinfo is not None
            except ValueError:
                ok = False
            if not ok:
                out.append({"instance_id": None, "code": "invalid_snapshot", "pointer": f"/selection/{key}",
                            "message": "is not a date-time with its time zone (ISO 8601)"})
    return out


def validate(snapshot) -> list[dict]:
    """Problems of a snapshot as [{instance_id, code, pointer, message}]; the input is not changed."""
    s = copy.deepcopy(snapshot)
    problems: list[dict] = []
    for err in sorted(_VALIDATOR.iter_errors(s), key=lambda e: [str(p) for p in e.path]):
        path = list(err.path)
        if err.validator == "required":
            present = err.instance if isinstance(err.instance, dict) else {}
            names = [n for n in err.validator_value if n not in present]
        else:
            names = [None]
        for name in names:
            full = path + ([name] if name else [])
            problems.append({
                "instance_id": _instance_id(s, full),
                "code": "invalid_snapshot",
                "pointer": "".join("/" + _printable(p) for p in full),
                "message": _message(err),
            })
    blocks = s.get("blocks") if isinstance(s, dict) else None
    if isinstance(blocks, list):
        seen: set = set()
        for i, b in enumerate(blocks):
            iid = b.get("instance_id") if isinstance(b, dict) else None
            if isinstance(iid, str):
                if iid in seen:
                    problems.append({"instance_id": _printable(iid), "code": "duplicate_instance_id",
                                     "pointer": f"/blocks/{i}/instance_id",
                                     "message": "is used by another block of this layout"})
                seen.add(iid)
    problems.extend(_surrogate_problems(s))
    problems.extend(_content_problems(s))
    return problems


def fingerprint(snapshot: dict) -> str:
    """SHA-256 of the canonical snapshot without mode, requested_by and document."""
    s = {k: v for k, v in snapshot.items() if k not in ("mode", "requested_by", "document")}
    raw = json.dumps(s, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def structure_problems(blocks) -> list[dict]:
    """Problems of the block list: a layout has one appendix at most."""
    problems: list[dict] = []
    seen = False
    for i, b in enumerate(blocks or ()):
        if isinstance(b, dict) and b.get("block_type") == "appendix":
            if seen:
                problems.append({"instance_id": b.get("instance_id"), "code": "duplicate_appendix",
                                 "pointer": f"/blocks/{i}", "message": "a layout has one appendix at most"})
            seen = True
    return problems
