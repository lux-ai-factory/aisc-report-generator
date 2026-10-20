"""The tools' own Pass / Fail, and assorted renderer fixes: the key figures tile, lone surrogates in a
snapshot, character references in DOCX links, prose annotations, and the "Write this section." placeholder.
"""
import copy
import io
import json
import zipfile

import pytest

from conftest import block, need, snapshot, soup, text
from v2_block_helpers import need_tool_package, one
from v2_core_helpers import H, TOKEN, blk, do_render, docx_all_text, docx_of, pdf_pages, snap

PLACEHOLDER = "Write this section."


def client_500_visible(deps):
    """A service client that turns a server error into a 500 answer instead of raising in the test."""
    from fastapi.testclient import TestClient

    return TestClient(need("report_service", "create_app")(deps=deps, token=TOKEN), raise_server_exceptions=False)


# The Promptfoo tile says "Pass".

@pytest.mark.db
def test_the_promptfoo_key_figure_tile_is_labelled_pass(deps):
    need_tool_package("aisc_report_plugin_promptfoo", "PROMPTFOOToolRenderer")
    _, _, node, _ = one(deps, "key_figures", figures=["tests"])
    tiles = [" ".join(el.get_text(" ").split()) for el in node.find_all(attrs={"data-figure": "tool"})]
    pf = [t for t in tiles if t.startswith("Promptfoo")]
    assert any(t.startswith("Promptfoo: Pass ") for t in pf), pf
    assert not any("Pass rate" in t for t in pf), pf


# A tool's own Fail is not a verdict of the report.

@pytest.mark.db
def test_verdict_stays_none_and_coverage_is_unchanged(deps):
    """LangBiTe's own Fail (All tolerance checks 0 of 4 on
    Mike v2) does not turn the linked objective into "evidence, attention"; verdict() is None."""
    for module, cls in (("aisc_report_plugin_langbite", "LANGBITEToolRenderer"),
                        ("aisc_report_plugin_strongreject", "STRONGREJECTToolRenderer"),
                        ("aisc_report_plugin_promptfoo", "PROMPTFOOToolRenderer")):
        need_tool_package(module, cls)
    links = [{"objective_id": "R1.1", "tests": ["LangBiTe"], "checklists": []},
             {"objective_id": "R2.1", "tests": ["Promptfoo", "StrongREJECT"], "checklists": []}]
    _, _, node, _ = one(deps, "summary_coverage", coverage_links=links)
    rows = {el["data-objective"]: text(el) for el in node.find_all(attrs={"data-objective": True})}
    assert "attention" not in rows["R1.1"] and "evidence" in rows["R1.1"], rows["R1.1"]
    assert "attention" not in rows["R2.1"] and "evidence" in rows["R2.1"], rows["R2.1"]


# A lone surrogate in a block's instance id or an option.

@pytest.mark.db
@pytest.mark.parametrize("mode", ["preview", "pdf", "docx"])
@pytest.mark.parametrize("field,pointer", [("instance_id", "/blocks/0/instance_id"),
                                           ("text", "/blocks/0/options/text")])
def test_a_lone_surrogate_in_the_instance_id_or_an_option_is_422(deps, mode, field, pointer):
    s = snapshot([block("free_text", text="x")], mode=mode)
    iid = s["blocks"][0]["instance_id"]
    (s["blocks"][0] if field == "instance_id" else s["blocks"][0]["options"])[field] = "SURROGATEHERE"
    raw = json.dumps(s).replace("SURROGATEHERE", "x\\ud800y")        # the JSON escape of a lone surrogate
    r = client_500_visible(deps).post("/v1/render", headers={**H, "Content-Type": "application/json"}, content=raw)
    assert r.status_code == 422, (r.status_code, r.text[:300])
    r.content.decode("utf-8")                                          # the body is valid UTF-8
    problems = r.json()["problems"]
    assert problems and all(p["code"] == "invalid_snapshot" for p in problems)
    expected_iid = "x\\ud800y" if field == "instance_id" else iid
    block_problems = [p for p in problems if p["pointer"].startswith("/blocks/0")]
    assert block_problems and all(p["instance_id"] == expected_iid for p in block_problems), block_problems
    assert any(p["pointer"] == pointer and p["message"] == "holds a lone surrogate" for p in problems), problems


# A character reference inside a link address in the DOCX export.

BAD_REFS = ["&#1;", "&#00001;", "&#x1F;", "&#65534;", "&#55296;"]


def _docx_of_html(html):
    html_to_docx = need("report_renderer.docx", "html_to_docx")
    return html_to_docx(html, title="t", subject="s", language="en", look=None, t=lambda s, **k: s)


@pytest.mark.parametrize("scheme", ["https://e.org/", "mailto:a@e.org"])
@pytest.mark.parametrize("ref", BAD_REFS)
def test_a_forbidden_character_in_a_link_address_keeps_the_text(ref, scheme):
    import docx
    from lxml import etree

    html = f'<html><body><p>Before <a href="{scheme}{ref}">Link text</a> after</p></body></html>'
    raw = _docx_of_html(html)
    body = docx_all_text(docx.Document(io.BytesIO(raw)))
    assert "Link text" in body and "Before" in body and "after" in body
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            if name.endswith(".rels") or name.endswith(".xml"):
                etree.fromstring(z.read(name))                          # every part is valid XML


def test_a_clean_link_address_keeps_its_hyperlink():
    """A normal address stays a hyperlink."""
    raw = _docx_of_html('<html><body><p><a href="https://e.org/a?b=1">Link text</a></p></body></html>')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        doc = z.read("word/document.xml").decode("utf-8")
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
    assert "<w:hyperlink" in doc and "https://e.org/a?b=1" in rels


# Built-in prose and identifier annotations.

def _string_leaves(node, path, under=False, out=None):
    out = [] if out is None else out
    if not isinstance(node, dict):
        return out
    under = under or bool(node.get("x-aisc-reference"))
    t = node.get("type")
    if t == "string" or (isinstance(t, list) and "string" in t):
        out.append((path, node, under))
    for k, v in (node.get("properties") or {}).items():
        _string_leaves(v, f"{path}/{k}", under, out)
    if isinstance(node.get("items"), dict):
        _string_leaves(node["items"], f"{path}/items", under, out)
    for key in ("oneOf", "anyOf", "allOf", "prefixItems"):
        for i, b in enumerate(node.get(key) or []):
            _string_leaves(b, f"{path}/{key}{i}", under, out)
    if isinstance(node.get("additionalProperties"), dict):
        _string_leaves(node["additionalProperties"], f"{path}/*", under, out)
    return out


def _block_types(deps):
    from fastapi.testclient import TestClient

    r = TestClient(need("report_service", "create_app")(deps=deps, token=TOKEN)).get("/v1/block-types", headers=H)
    assert r.status_code == 200
    return {t["type_id"]: t for t in r.json()}


@pytest.mark.db
def test_every_built_in_string_leaf_is_classified(deps):
    unclassified = []
    for type_id, t in _block_types(deps).items():
        for path, node, under_ref in _string_leaves(t["options_schema"], type_id):
            ml = node.get("maxLength")
            if ("x-aisc-prose" in node or (ml is not None and ml <= 300) or under_ref
                    or any(k in node for k in ("enum", "const", "pattern", "format"))):
                continue
            unclassified.append(path)
    assert not unclassified, f"string options with no x-aisc-prose, no short maxLength: {unclassified}"


@pytest.mark.db
def test_the_named_options_carry_their_annotation(deps):
    types = _block_types(deps)

    def prop(type_id, name):
        return types[type_id]["options_schema"]["properties"][name]

    def item_branch(type_id, name):
        node = prop(type_id, name)
        branches = [b for b in node.get("oneOf", [node]) if b.get("type") == "array"]
        assert branches, (type_id, name)
        return branches[0]["items"]

    assert prop("free_text", "text").get("x-aisc-prose") is True
    assert prop("chapter", "intro").get("x-aisc-prose") is True
    for type_id in types:
        assert prop(type_id, "commentary").get("x-aisc-prose") is True, type_id
    for type_id, name in (("control_objectives", "requirements"), ("summary_coverage", "requirements"),
                          ("test_results", "tools")):
        assert item_branch(type_id, name).get("x-aisc-prose") is False, (type_id, name)
    assert prop("chart", "dimension").get("x-aisc-prose") is False
    for type_id, name in (("cover", "report_title"), ("cover", "subtitle")):
        assert "x-aisc-prose" not in prop(type_id, name), (type_id, name)


# The placeholder "Write this section." is left out.

def _placeholder_layout(text_value=PLACEHOLDER):
    ids = [f"00000000-0000-4000-8000-00000000f8{i:02d}" for i in range(5)]
    blocks = [blk("free_text", ids[0], title="First", text="One."),
              blk("chapter", ids[1], title="Chap"),
              blk("free_text", ids[2], title="Unwritten", text=text_value, format="markdown"),
              blk("ai_card", ids[3]),
              blk("free_text", ids[4], title="Last", text="Two.")]
    return blocks, ids


@pytest.mark.db
@pytest.mark.parametrize("value", [PLACEHOLDER, "  Write this section.\n"])
def test_an_unwritten_free_text_is_left_out_of_the_preview(deps, value):
    blocks, ids = _placeholder_layout(value)
    result = do_render(deps, snap(blocks, document={"toc": "on", "numbering": True}, snapshot_version=2))
    doc = soup(result["html"])
    assert doc.find(id=f"block-{ids[2]}") is None, "the unwritten section is still printed"
    assert "Unwritten" not in text(doc.find(id="toc")) and PLACEHOLDER not in result["html"]
    heads = {i: text(doc.find(id=f"block-{i}").find(["h1", "h2"])) for i in (ids[0], ids[1], ids[3], ids[4])}
    assert heads[ids[0]].startswith("1 ") and heads[ids[1]] == "2 Chap"
    assert heads[ids[3]].startswith("2.1 "), heads
    assert [s["instance_id"] for s in result["block_statuses"]] == ids
    st = result["block_statuses"][2]
    assert st["status"] == "empty" and "Not written yet: left out of the report." in st["notices"], st


@pytest.mark.db
def test_an_unwritten_free_text_is_left_out_of_pdf_and_docx(deps):
    blocks, _ = _placeholder_layout()
    s = snap(blocks, document={"toc": "on", "numbering": True}, snapshot_version=2)
    pdf_text = " ".join(pdf_pages(do_render(deps, dict(s, mode="pdf"))))
    assert PLACEHOLDER not in pdf_text and "Unwritten" not in pdf_text
    body = docx_all_text(docx_of(do_render(deps, dict(s, mode="docx"))))
    assert PLACEHOLDER not in body and "Unwritten" not in body
    assert "One." in body and "Two." in body


@pytest.mark.db
def test_a_placeholder_commentary_is_not_printed(deps):
    plain = blk("ai_card", "00000000-0000-4000-8000-00000000f901")
    withc = blk("ai_card", plain["instance_id"], commentary=PLACEHOLDER)
    assert do_render(deps, snap([withc]))["html"] == do_render(deps, snap([plain]))["html"]


@pytest.mark.db
def test_a_placeholder_chapter_intro_is_not_printed(deps):
    iid = "00000000-0000-4000-8000-00000000f902"
    empty = [blk("chapter", iid, title="C", intro=""), blk("ai_card", "00000000-0000-4000-8000-00000000f903")]
    unwritten = copy.deepcopy(empty)
    unwritten[0]["options"]["intro"] = PLACEHOLDER
    assert do_render(deps, snap(unwritten))["html"] == do_render(deps, snap(empty))["html"]


# A layout straight from a built-in preset prints no placeholder.

#: the block lists of the composer's built-in presets eu-ai-act and internal-audit (toc on, numbering on)
PRESETS = {
    "eu-ai-act": [["cover", {}], ["key_figures", {}], ["chapter", {"title": "System and risks"}], ["ai_card", {}],
                  ["risk_classification", {}], ["chapter", {"title": "Control objectives"}],
                  ["control_objectives", {"show_severity": True}], ["summary_coverage", {}],
                  ["chapter", {"title": "Evidence"}], ["test_results", {}], ["control_answers", {}],
                  ["appendix", {}],
                  ["free_text", {"title": "Method", "text": PLACEHOLDER, "format": "markdown"}]],
    "internal-audit": [["cover", {}], ["free_text", {"title": "Scope", "text": PLACEHOLDER, "format": "markdown"}],
                       ["key_figures", {}], ["control_answers", {}], ["test_results", {}],
                       ["summary_coverage", {"show_uncovered_only": True}],
                       ["free_text", {"title": "Findings", "text": PLACEHOLDER, "format": "markdown"}]],
}


@pytest.mark.db
@pytest.mark.parametrize("preset", sorted(PRESETS))
def test_a_preset_layout_generated_at_once_has_no_placeholder(deps, preset):
    blocks = [blk(bt, **opts) for bt, opts in PRESETS[preset]]
    s = snap(blocks, project="M", system="M_V2", snapshot_version=2, document={"toc": "on", "numbering": True})
    pdf_text = " ".join(pdf_pages(do_render(deps, dict(s, mode="pdf"))))
    assert PLACEHOLDER not in " ".join(pdf_text.split())
    body = docx_all_text(docx_of(do_render(deps, dict(s, mode="docx"))))
    assert PLACEHOLDER not in body
