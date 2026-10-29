"""A risk's rating, from its rating_impact and rating_likelihood.

rating = impact x likelihood (1 to 25); until both are set the risk is "not rated" (None), as in step 2.
Bands: Low 1-4, Medium 5-9, High 10-16, Critical 17-25. Pure, no database.
"""
import pytest

from conftest import need


def rating(*a):
    return need("report_renderer.rating", "rating")(*a)


def band(*a):
    return need("report_renderer.rating", "band")(*a)


@pytest.mark.parametrize("impact,likelihood,expected", [
    (5, 4, 20), (1, 1, 1), (5, 5, 25), (5, None, None), (None, 4, None), (3, None, None), (None, None, None),
])
def test_rating_is_impact_times_likelihood_once_both_are_set(impact, likelihood, expected):
    assert rating(impact, likelihood) == expected


@pytest.mark.parametrize("value,expected", [
    (1, "Low"), (4, "Low"), (5, "Medium"), (9, "Medium"), (10, "High"), (16, "High"),
    (17, "Critical"), (25, "Critical"), (None, None),
])
def test_band_edges(value, expected):
    assert band(value) == expected


def test_bands_in_report_order():
    assert need("report_renderer.rating", "BANDS") == ("Critical", "High", "Medium", "Low")


def test_no_value_stands_in_for_a_missing_part():
    import report_renderer.rating as module

    assert not hasattr(module, "UNRATED_COUNTS_AS")
