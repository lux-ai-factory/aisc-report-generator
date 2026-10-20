"""The composer's five built-in layouts hold only options this
renderer accepts, and no option that names a project's data (they are shared by every project)."""
import json

import pytest

from conftest import AISC_INSTALL

PRESETS = AISC_INSTALL / "apps/report-composer/report_composer/presets"
ORDER = ["summary", "management-overview", "assessment-report", "eu-ai-act", "technical-dossier"]


def _registry():
    from report_renderer.registry import build_registry

    return build_registry(entry_points=[])


@pytest.mark.parametrize("slug", ORDER)
def test_every_block_of_a_built_in_is_valid_for_the_renderer(slug):
    doc = json.loads((PRESETS / f"{slug}.json").read_text(encoding="utf-8"))
    reg = _registry()
    for i, b in enumerate(doc["blocks"]):
        cls = reg.block(b["block_type"])
        assert cls is not None, (slug, i, b["block_type"])
        options = {**cls.full_default_options(), **b["options"]}
        assert cls.options_problems(options) == [], (slug, i, b["block_type"], cls.options_problems(options))


@pytest.mark.parametrize("slug", ORDER)
def test_no_built_in_names_a_projects_data(slug):
    doc = json.loads((PRESETS / f"{slug}.json").read_text(encoding="utf-8"))
    reg = _registry()
    for i, b in enumerate(doc["blocks"]):
        props = reg.block(b["block_type"]).options_schema.get("properties", {})
        refs = {n for n, p in props.items() if p.get("x-aisc-reference")}
        assert not refs & set(b["options"]), (slug, i, refs & set(b["options"]))
