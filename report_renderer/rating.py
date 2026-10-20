"""A risk's rating.

A risk carries an impact and a likelihood, each 1 to 5 or unrated. Its rating is impact x likelihood
(1 to 25), an unrated part counting 3; a risk with both parts unrated is not rated (None).
Bands: Low 1-4, Medium 5-9, High 10-16, Critical 17-25.
"""
from __future__ import annotations

UNRATED_COUNTS_AS = 3
BANDS = ("Critical", "High", "Medium", "Low")
_LOWEST = ((17, "Critical"), (10, "High"), (5, "Medium"), (1, "Low"))


def rating(impact: int | None, likelihood: int | None) -> int | None:
    if impact is None and likelihood is None:
        return None
    return (UNRATED_COUNTS_AS if impact is None else impact) * (UNRATED_COUNTS_AS if likelihood is None else likelihood)


def band(value: int | None) -> str | None:
    if value is None:
        return None
    for lowest, name in _LOWEST:
        if value >= lowest:
            return name
    return None
