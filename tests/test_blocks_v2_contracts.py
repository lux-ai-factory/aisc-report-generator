"""Reference markers and options of the built-in blocks. The contract versions are pinned in
test_service_v2.py."""
import pytest

from conftest import need


def _registry():
    return need("report_renderer.registry", "build_registry")(entry_points=[])


# reference options are marked, so presets strip them
@pytest.mark.parametrize("type_id,option", [("test_results", "metrics"), ("chart", "tool_chart"),
                                            ("control_objectives", "objectives")])
def test_reference_options_are_marked(type_id, option):
    cls = _registry().block(type_id)
    if cls is None:
        pytest.fail(f"missing feature: built-in block type {type_id}", pytrace=False)
    props = cls.full_options_schema()["properties"]
    if option not in props:
        pytest.fail(f"missing feature: option {option} of block {type_id}", pytrace=False)
    assert props[option].get("x-aisc-reference") is True


@pytest.mark.parametrize("type_id,option", [("chart", "dataset"), ("key_figures", "figures"),
                                            ("changes_since", "sections"), ("control_objectives", "requirements")])
def test_structural_options_are_not_references(type_id, option):
    cls = _registry().block(type_id)
    if cls is None:
        pytest.fail(f"missing feature: built-in block type {type_id}", pytrace=False)
    props = cls.full_options_schema()["properties"]
    assert option in props, f"missing feature: option {option} of block {type_id}"
    assert not props[option].get("x-aisc-reference")


# test_results options and defaults
def test_test_results_new_defaults():
    d = _registry().block("test_results").full_default_options()
    for key, value in (("metrics", "all"), ("show_charts", True), ("detail", "full")):
        assert d.get(key) == value, f"missing feature: test_results.{key} default {value!r}"


def test_detail_values():
    cls = _registry().block("test_results")
    props = cls.full_options_schema()["properties"]
    assert "detail" in props, "missing feature: test_results.detail"
    assert cls.options_problems({**cls.full_default_options(), "detail": "summary"}) == []
    assert cls.options_problems({**cls.full_default_options(), "detail": "short"})
