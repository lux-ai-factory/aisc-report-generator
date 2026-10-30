"""Compatibility pins against the goldens of tests/golden/.

The goldens were captured from the renderer at 41d11b9 (tests/golden/capture.py; MANIFEST.json names
the commit). A snapshot that uses none of the optional snapshot keys must render the same:
- Alpha v2 and Mike v2 (evaluations): identical except inside the Test results section.
- Alpha v2 with legacy links: identical except the second summary block.
"""
import json
import re
import sys
from pathlib import Path

import pytest

from conftest import need
from v2_core_helpers import pdf_pages, split_sections

GOLDEN = Path(__file__).resolve().parent / "golden"
sys.path.insert(0, str(GOLDEN))
from golden_cases import CASES, SECOND_SUMMARY_IID, TEST_RESULTS_IID, snapshot_for  # noqa: E402

pytestmark = pytest.mark.db


@pytest.fixture
def gdeps(make_deps):
    return make_deps(images=need("report_renderer.superset", "NoImageProvider")())


def golden(name: str, ext: str = "html") -> str:
    return (GOLDEN / f"{name}.{ext}").read_text(encoding="utf-8")


def render_case(gdeps, name, mode="preview"):
    return need("report_renderer.document", "render")(snapshot_for(CASES[name], mode), gdeps)


def test_the_goldens_come_from_the_renderer_before_the_run():
    manifest = json.loads((GOLDEN / "MANIFEST.json").read_text())
    assert manifest["renderer_commit"] == "41d11b9"
    assert set(manifest["cases"]) == set(CASES)


def test_every_golden_file_belongs_to_a_case():
    names = {p.name for p in GOLDEN.iterdir() if p.suffix in (".html", ".json") and p.name != "MANIFEST.json"}
    expected = {f"{n}.html" for n in CASES} | {f"{n}.statuses.json" for n in CASES}
    expected |= {f"{n}.pdf.json" for n, case in CASES.items() if case.get("pdf")}
    assert names == expected


# With evaluations: only the Test results section may change.

def _assert_same_except(html_now: str, html_then: str, allowed: set[str]):
    shell_now, sec_now = split_sections(html_now)
    shell_then, sec_then = split_sections(html_then)
    assert shell_now == shell_then, "the document outside the sections changed"
    assert list(sec_now) == list(sec_then), "the sections or their order changed"
    for key, then in sec_then.items():
        if key in allowed:
            continue
        assert sec_now[key] == then, f"section {key} changed"


@pytest.mark.parametrize("name", ["a_v2_live", "a_v2_live_styled", "m_v2_live_styled"])
def test_with_evaluations_only_the_test_results_section_may_change(gdeps, name):
    _assert_same_except(render_case(gdeps, name)["html"], golden(name), {TEST_RESULTS_IID})


def test_the_mystery_tool_keeps_its_generic_table(gdeps):
    """Only LangBiTe, StrongREJECT and promptfoo get their own section: other tools keep the generic table."""
    _, now = split_sections(render_case(gdeps, "a_v2_live")["html"])
    _, then = split_sections(golden("a_v2_live"))
    table = re.compile(r'<table class="measurements">.*?</table>', re.S)
    mystery_then = [t for t in table.findall(then[TEST_RESULTS_IID]) if "mystery_metric" in t]
    assert mystery_then, "golden has the Mystery Tool table"
    assert mystery_then[0] in now[TEST_RESULTS_IID]


def test_legacy_links_only_the_second_summary_block_may_change(gdeps):
    """Without a coverage_links key the first summary block's own links apply."""
    _assert_same_except(render_case(gdeps, "a_v2_legacy_links")["html"], golden("a_v2_legacy_links"),
                        {TEST_RESULTS_IID, SECOND_SUMMARY_IID})


# The a_v2_live_styled PDF golden.

_MARGIN = re.compile(r"^(Alpha project, Version 2|Page \d+ of \d+)$")
_MARKER = re.compile(r"^(•|\d+\.)\s*$")


def _flow_lines(pages) -> list[str]:
    """The PDF text as one flow: margin boxes, lone list markers (pypdf puts them at the page end) and
    TOC page numbers removed, so only a change of content shows."""
    out = []
    for page in pages:
        for line in page.splitlines():
            line = line.rstrip()
            if not line.strip() or _MARGIN.match(line.strip()) or _MARKER.match(line.strip()):
                continue
            out.append(re.sub(r"\s*\.{3,}\s*\d+$", "", line))
    return out


_TABLE_HEADS = {"Objective Label Description Tests Checklists Coverage", "Question Article Answer Score", "Metric Value Unit",
                "Name Type AIRO property Object"}


def _without_repeated_heads(lines) -> list[str]:
    """A table header repeated on a new page depends only on where the page breaks: keep the first one."""
    seen, out = set(), []
    for ln in lines:
        if ln in _TABLE_HEADS:
            if ln in seen:
                continue
            seen.add(ln)
        out.append(ln)
    return out


def _outside_test_results(lines) -> tuple[list[str], list[str]]:
    """(text before the Test results heading, text from the Checklist answers heading on); the TOC's own
    entries are skipped by taking the last heading occurrence before the section's first notice."""
    start = max(i for i, ln in enumerate(lines) if ln == "Test results" and i + 1 < len(lines)
                and lines[i + 1].startswith("Newer results exist"))
    end = next(i for i in range(start, len(lines)) if lines[i] == "Checklist answers")
    return _without_repeated_heads(lines[:start]), _without_repeated_heads(lines[end:])


def test_pdf_text_with_evaluations_only_the_test_results_section_may_change(gdeps):
    """The same rule on the PDF (a_v2_live_styled.pdf.json, captured at 41d11b9): every text outside
    the Test results section is the same, and the section still starts and ends in the same place."""
    now = _flow_lines(pdf_pages(render_case(gdeps, "a_v2_live_styled", mode="pdf")))
    then = _flow_lines(json.loads(golden("a_v2_live_styled", "pdf.json")))
    before_now, after_now = _outside_test_results(now)
    before_then, after_then = _outside_test_results(then)
    assert "Control objectives" in before_then and "Mean score 2.5, answered 2 of 4" in after_then
    assert before_now == before_then
    assert after_now == after_then
