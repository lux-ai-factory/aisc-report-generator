"""A risk's rating.

A risk carries an impact and a likelihood, each 1 to 5 or unrated. Its rating is impact x likelihood
(1 to 25) once both are set; until then it is not rated (None), counts towards no score and has no band,
as in step 2. Bands: Low 1-4, Medium 5-9, High 10-16, Critical 17-25.
"""
from __future__ import annotations

BANDS = ("Critical", "High", "Medium", "Low")
_LOWEST = ((17, "Critical"), (10, "High"), (5, "Medium"), (1, "Low"))


def rating(impact: int | None, likelihood: int | None) -> int | None:
    if impact is None or likelihood is None:
        return None
    return impact * likelihood


def band(value: int | None) -> str | None:
    if value is None:
        return None
    for lowest, name in _LOWEST:
        if value >= lowest:
            return name
    return None
