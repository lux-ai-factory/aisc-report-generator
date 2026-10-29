"""Languages: every report is in English.

The renderer ships only report_renderer/i18n/en.json (which may hold English singular forms
"<msgid>|one"), REPORT_I18N_PATH is not read, and a snapshot's language (any pattern-valid code)
renders English.
"""
import ast
import json
import re
from pathlib import Path

import pytest

from conftest import IDS, need, soup, text
from v2_core_helpers import H, blk, do_render, service, snap

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "report_renderer" / "i18n"


def catalogue(code):
    path = I18N / f"{code}.json"
    assert path.is_file(), f"missing feature: report_renderer/i18n/{code}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# The catalogue.

def test_en_catalogue_has_the_format_and_is_the_only_one():
    en = catalogue("en")
    assert en["_meta"]["code"] == "en" and en["_meta"]["name"] == "English"
    assert "plural_one" not in en["_meta"], "English keeps the default plural rule [1]"
    assert sorted(p.name for p in I18N.glob("*.json")) == ["en.json"], "fr.json is deleted"
    assert all(k.endswith("|one") for k in en.get("messages", {})), "en.json holds only |one entries"
    assert en.get("messages"), "missing feature: en.json gives English singular forms"


_T_CALL = re.compile(r"""\bt\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")


def collected_msgids() -> set[str]:
    """Every t("...") message id in the renderer's Python (AST) and templates (regex)."""
    ids: set[str] = set()
    for py in (ROOT / "report_renderer").rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and ((isinstance(node.func, ast.Name) and node.func.id == "t")
                         or (isinstance(node.func, ast.Attribute) and node.func.attr == "t"))):
                ids.add(node.args[0].value)
    for tpl in (ROOT / "report_renderer").rglob("*.j2"):
        for m in _T_CALL.finditer(tpl.read_text(encoding="utf-8")):
            ids.add(m.group(1) if m.group(1) is not None else m.group(2))
    return ids


# t().

@pytest.mark.db
def test_t_fills_placeholders_and_never_raises(deps):
    context_for = need("report_renderer.context", "context_for")
    ctx = context_for(IDS["A"], IDS["A_V2"], deps=deps, mode="preview")
    t = getattr(ctx, "t", None)
    assert callable(t), "missing feature: BlockContext.t"
    assert ctx.language == "en"
    assert t("Newer results exist for version {number}.", number=3) == "Newer results exist for version 3."
    assert t("Newer results exist for version {number}.") == "Newer results exist for version {number}."
    assert t("A text nobody translated {x}", x=1) == "A text nobody translated 1"


# No language can be added.

@pytest.mark.db
def test_a_catalogue_in_report_i18n_path_is_ignored(deps, tmp_path, monkeypatch):
    (tmp_path / "de.json").write_text(json.dumps(
        {"_meta": {"code": "de", "name": "Deutsch", "decimal_separator": ",", "percent_format": "{value} %"},
         "messages": {"Contents": "Inhalt"}}), encoding="utf-8")
    monkeypatch.setenv("REPORT_I18N_PATH", str(tmp_path))
    client = service(deps)
    langs = client.get("/health", headers=H).json()["languages"]
    assert langs == [{"code": "en", "name": "English"}]
    r = client.post("/v1/render", headers=H,
                    json=snap([blk("free_text", title=x, text=x) for x in "abcd"]))
    assert r.status_code == 200, r.text[:300]
    html = r.json()["html"]
    assert text(soup(html).find(id="toc").find("h2")) == "Contents"
    assert soup(html).html.get("lang") == "en"


# What is translated.

@pytest.mark.db
def test_english_stays_the_default(deps):
    """Compatibility pin: without a language the report renders English with lang="en"."""
    html = do_render(deps, snap([blk("free_text", title=x, text=x) for x in "abcd"]))["html"]
    assert soup(html).html.get("lang") == "en" and "Contents" in html


@pytest.mark.db
def test_fixed_texts_are_english(deps):
    cover = blk("cover", report_title="Rapport Example Assistant")
    ft = blk("free_text", title="Mon titre", text="User text stays as written.")
    tr = blk("test_results")
    card = blk("ai_card")
    result = do_render(deps, snap([cover, ft, card, tr], project="A", system="A_V1"))
    html = result["html"]
    doc = soup(html)
    assert doc.html.get("lang") == "en"
    assert text(doc.find(id="toc").find("h2")) == "Contents"
    all_text = text(doc)
    assert "Newer results exist for version 2." in all_text
    for kept in ("Rapport Example Assistant", "Mon titre", "User text stays as written.", "Alpha scorer", "LangBiTe"):
        assert kept in all_text
    card_h2 = text(doc.find(id=f"block-{card['instance_id']}").find("h2"))
    assert card_h2 == "AI card"


@pytest.mark.db
def test_dates_stay_iso_numbers_use_the_decimal_point(deps):
    tr = blk("test_results", tools="all")
    cover = blk("cover")
    html = do_render(deps, snap([cover, tr]))["html"]
    sec_text = text(soup(html).find(id=f"block-{tr['instance_id']}"))
    assert "0.125" in sec_text and "0,125" not in sec_text
    assert "2026-09-20" in text(soup(html).find(id=f"block-{cover['instance_id']}"))


@pytest.mark.db
def test_page_x_of_y_is_english_in_the_pdf_css(deps):
    html = do_render(deps, snap([blk("free_text", text="x")]))["html"]
    css = soup(html).find("style").string
    assert '"Page " counter(page) " of "' in css


def test_every_singular_form_belongs_to_a_used_message():
    """Checked over en.json, the only catalogue."""
    ids = collected_msgids()
    for key in catalogue("en").get("messages", {}):
        if key.endswith("|one"):
            assert key[:-len("|one")] in ids, f"singular form of an unused message: {key!r}"
