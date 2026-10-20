"""The order objectives are listed in.

Built-in objectives first, by number (O9 before O10, which string order would not give); then a
project's own sets by code and number (BNK9 before BNK10); any other id last."""
from __future__ import annotations

import re


def objective_order(objective_id: str) -> tuple:
    found = re.fullmatch(r"(O|[A-Z]{2,6})([1-9][0-9]*)", objective_id)
    if found is None:
        return (2, "", 0, objective_id)
    code, number = found.groups()
    return (0 if code == "O" else 1, code, int(number), "")
