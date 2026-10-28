"""Every report is in English, whatever language the snapshot names, and English messages take their
singular form when a count is one (renderer side).
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

from conftest import IDS, need, soup
from v2_core_helpers import H, blk, do_render, docx_all_text, docx_of, service, snap, split_sections

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "report_renderer" / "i18n"


def translator_en():
    translator = need("report_renderer.languages", "translator")
    t, _ = translator()
    return t


# /health lists English only.

@pytest.mark.db
def test_health_is_english_only(deps):
    client = service(deps)
    langs = client.get("/health", headers=H).json().get("languages", [])
    assert [x if isinstance(x, str) else x.get("code") for x in langs] == ["en"]


# Any pattern-valid language renders English.

def _blocks():
    ids = [f"00000000-0000-4000-8000-00000000d1{i:02d}" for i in range(6)]
    return [blk("cover", ids[0], report_title="R"), blk("key_figures", ids[1]),
            blk("chapter", ids[2], title="Chapter one", intro="Intro."),
            blk("test_results", ids[3], commentary="Some **commentary**."),
            blk("control_objectives", ids[4]), blk("free_text", ids[5], text="Text.")]


def _snap(language, mode="preview"):
    extra = {} if language is None else {"language": language}
    return snap(_blocks(), project="M", system="M_V2", mode=mode, snapshot_version=2,
                document={"toc": "on", "numbering": True}, **extra)


@pytest.mark.db
@pytest.mark.parametrize("language", ["en", "fr", "de", "xx", "fr-BE"])
def test_any_pattern_valid_language_is_accepted_and_renders_english(deps, language):
    r = service(deps).post("/v1/render", headers=H, json=_snap(language))
    assert r.status_code == 200, r.text[:300]
    html = r.json()["html"]
    assert soup(html).html.get("lang") == "en"
    assert html == do_render(deps, _snap(None))["html"]


@pytest.mark.db
def test_docx_text_and_language_property_are_english_with_fr(deps):
    en = docx_of(do_render(deps, _snap(None, mode="docx")))
    fr = docx_of(do_render(deps, _snap("fr", mode="docx")))
    assert fr.core_properties.language == "en"
    assert docx_all_text(fr) == docx_all_text(en)


# The fingerprint is computed over the snapshot as received.

@pytest.mark.db
def test_the_fingerprint_keeps_its_definition_for_a_fr_snapshot(deps):
    """The fingerprint of a snapshot with language "fr" is the SHA-256 of
    the snapshot as received (without mode, requested_by and document), so stored reports keep theirs."""
    s = _snap("fr")
    canonical = {k: v for k, v in s.items() if k not in ("mode", "requested_by", "document")}
    expected = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode("utf-8")).hexdigest()
    assert do_render(deps, s)["fingerprint"] == expected
    assert do_render(deps, _snap("en"))["fingerprint"] != expected


# The block context is English.

@pytest.mark.db
def test_the_context_is_english_whatever_the_language(deps):
    context_for = need("report_renderer.context", "context_for")
    ctx = context_for(IDS["M"], IDS["M_V2"], deps=deps, mode="preview", language="fr")
    assert ctx.language == "en"
    assert ctx.t("Contents") == "Contents"
    assert ctx.decimal_separator == "." and ctx.percent_format == "{value}%"
    assert ctx.t("{count} evaluations", count=1) == "1 evaluation"


@pytest.mark.db
def test_translate_for_uses_the_package_en_json_then_the_renderer(deps):
    pytest.importorskip("aisc_report_plugin_langbite", reason="optional tool renderer, not installed")
    pytest.importorskip("aisc_report_plugin_strongreject", reason="optional tool renderer, not installed")
    context_for = need("report_renderer.context", "context_for")
    ctx = context_for(IDS["M"], IDS["M_V2"], deps=deps, mode="preview", language="fr")
    lb = ctx.translate_for("aisc_report_plugin_langbite")
    msg = "Overall pass rate: {rate} across {groups} groups"
    assert lb(msg, rate="50%", groups=1) == "Overall pass rate: 50% across 1 group"
    assert lb(msg, rate="50%", groups=4) == "Overall pass rate: 50% across 4 groups"
    sr = ctx.translate_for("aisc_report_plugin_strongreject")          # ships no en.json, so the renderer's own is used
    assert sr("{count} evaluations", count=1) == "1 evaluation"
    assert sr("A text in no catalogue {x}", x=2) == "A text in no catalogue 2"


# English singular forms.

SINGULARS = [
    ("{count} evaluations", "{count} evaluation"),
    ("in {count} requirement groups", "in {count} requirement group"),
    ("{count} answers were given for other versions and are not shown.",
     "{count} answer was given for another version and is not shown."),
    ("{count} evaluations are not tied to a version and are not shown.",
     "{count} evaluation is not tied to a version and is not shown."),
    ("{count} more groups are not shown.", "{count} more group is not shown."),
    ("{count} observations could not be tied to a tool.", "{count} observation could not be tied to a tool."),
    ("{count} selected checklists are not in this project and are not shown.",
     "{count} selected checklist is not in this project and is not shown."),
    ("{name} ({size} bytes)", "{name} ({size} byte)"),
]


def _params(msgid, n):
    return {"name": "log.txt", "size": n} if "{size}" in msgid else {"count": n}


@pytest.mark.parametrize("msgid,singular", SINGULARS, ids=[m for m, _ in SINGULARS])
def test_english_singular_form(msgid, singular):
    t = translator_en()
    assert t(msgid, **_params(msgid, 1)) == singular.format_map(_params(msgid, 1))
    for n in (0, 3):                                    # 0 stays plural in English
        assert t(msgid, **_params(msgid, n)) == msgid.format_map(_params(msgid, n))


def test_nouns_after_the_total_need_no_singular():
    t = translator_en()
    assert t("{count} of {total} objectives with evidence", count=1, total=4) == "1 of 4 objectives with evidence"
    assert t("{answered} of {total} questions answered", answered=1, total=3) == "1 of 3 questions answered"
    assert t("{tools}, +{count} more", tools="A, B", count=1) == "A, B, +1 more"


def test_the_singular_keys_are_exactly_the_listed_ones():
    """The singular keys of en.json are exactly the messages in SINGULARS: add a new one to both."""
    en = json.loads((I18N / "en.json").read_text(encoding="utf-8"))
    assert sorted(en.get("messages", {})) == sorted(m + "|one" for m, _ in SINGULARS)


# The one intended English change in the golden outputs.

GOLDEN = Path(__file__).resolve().parent / "golden"


@pytest.mark.db
@pytest.mark.parametrize("name", ["a_v2_live", "a_v2_live_styled", "a_v2_legacy_links"])
def test_one_observation_is_singular_in_the_test_results_section(make_deps, name):
    sys.path.insert(0, str(GOLDEN))
    from golden_cases import CASES, TEST_RESULTS_IID, snapshot_for

    gdeps = make_deps(images=need("report_renderer.superset", "NoImageProvider")())
    html = do_render(gdeps, snapshot_for(CASES[name], "preview"))["html"]
    _, sections = split_sections(html)
    tr = sections[TEST_RESULTS_IID]
    assert "1 observation could not be tied to a tool." in tr
    assert "1 observations" not in html
    golden = (GOLDEN / f"{name}.html").read_text(encoding="utf-8")
    # the goldens were recaptured after the fix: they hold the singular too
    assert "1 observation could not be tied to a tool." in split_sections(golden)[1][TEST_RESULTS_IID]
