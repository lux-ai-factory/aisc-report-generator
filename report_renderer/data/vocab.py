"""Labels: the qualification's AIRO vocabulary and the AI Act objectives list.

The qualification tables hold VAIR local names, shown here by their labels in the generated
vair_vocab.json. A value that is not a term, or a report without the file, shows the value itself,
so a card saved with older ids still reads correctly."""
from __future__ import annotations

import csv
import functools
import json


@functools.lru_cache(maxsize=8)
def airo_labels(path, vair_path=None) -> dict:
    with open(path, encoding="utf-8") as f:
        vocab = json.load(f)
    vair: dict[str, dict[str, str]] = {}
    if vair_path:
        with open(vair_path, encoding="utf-8") as f:
            vair = {cls: {t["id"]: t["label"] for t in terms} for cls, terms in json.load(f)["classes"].items()}
    return {
        # our operator/user, and VAIR's groups of affected people (AISubject) by VAIR's labels
        "affected": {**{e["id"]: e.get("label", e["id"]) for e in vocab.get("affected", [])},
                     **vair.get("AISubject", {})},
        # an older card's ids keep their old labels; VAIR's areas are named by VAIR
        "impactArea": {**{e["id"]: e.get("label", e["id"]) for e in vocab.get("impactArea", [])},
                       **vair.get("AreaOfImpact", {})},
        "vair": vair,
    }


def vair_label(vocab: dict, cls: str, value):
    """The VAIR label of `value` under `cls`, or `value` itself."""
    return (vocab.get("vair") or {}).get(cls, {}).get(value, value)


#: The class of each tag column's terms.
TAG_CLASSES = {"target_system_tags": "AICapability", "sector_tags": "Domain",
               "market_form_tags": "Modality", "locality_tags": "LocalityOfUse"}


@functools.lru_cache(maxsize=8)
def objective_labels(path) -> dict:
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            out[row["ID"]] = {"macro": row.get("Macro_Requirement", ""), "legal_basis": row.get("Legal_Basis", ""),
                              "label": row.get("Sub_Requirement_Label", ""),
                              "objective": row.get("Control_Objective", "")}
    return out


def with_own_objectives(labels: dict, own: list[dict]) -> dict:
    """The built-in objectives' labels and the project's own, in the same shape; an own objective's requirement is its dimension, named as the built-in set names it."""
    macros = {entry["macro"].split(" ", 1)[0]: entry["macro"] for entry in labels.values() if entry.get("macro")}
    out = dict(labels)
    for row in own:
        out[row["objective_id"]] = {"macro": macros.get(row["dimension"], row["dimension"]),
                                    "legal_basis": row.get("legal_basis") or "",
                                    "label": row["label"], "objective": row["text"]}
    return out
