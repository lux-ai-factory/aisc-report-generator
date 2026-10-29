"""The snapshot, version 3 (the only one): the docx mode, the document, the style's header and footer,
coverage links.

Every key past the required ones is optional and checked by snapshot.SCHEMA; a version other than 3 is refused.
"""
import pytest

from conftest import block, need, snapshot


def validate(s):
    return need("report_renderer.snapshot", "validate")(s)


def pointers(problems):
    return {p["pointer"] for p in problems}


def v2(**extra):
    s = snapshot([block("free_text", text="x")])
    s.update(extra)
    return s


GOOD_V2 = dict(
    snapshot_version=3,
    document={"id": "22222222-2222-4222-8222-222222222222", "toc": "on", "numbering": True},
    coverage_links=[{"objective_id": "R1.1", "tests": ["LangBiTe"], "checklists": ["cl-1"]}],
    style={"font": "inter", "font_size_pt": 10, "primary_color": "#000fdf", "accent_color": "#ff007e",
           "header_text": "{project}", "footer_text": "Internal use", "marking": "confidential",
           "show_document_id": True},
)


def test_a_snapshot_with_only_the_required_keys_passes():
    s = snapshot([block("free_text", text="x")])
    assert validate(s) == []


def test_a_snapshot_that_names_no_version_is_read_as_version_3():
    s = snapshot([block("free_text", text="x")])
    del s["snapshot_version"]
    assert validate(s) == []


@pytest.mark.parametrize("version", [1, 2])
def test_versions_1_and_2_are_refused(version):
    assert "/snapshot_version" in pointers(validate(v2(snapshot_version=version)))


def test_the_snapshot_names_no_language():
    """Reports are English only: the schema has no language key."""
    assert "language" not in need("report_renderer.snapshot", "SCHEMA")["properties"]


def test_the_table_of_contents_is_on_or_off():
    assert "/document/toc" in pointers(validate(v2(document={"toc": "auto"})))
    assert validate(v2(document={"toc": "on"})) == [] and validate(v2(document={"toc": "off"})) == []


def test_a_full_v2_snapshot_passes():
    assert validate(v2(**GOOD_V2)) == []


def test_mode_docx_is_accepted():
    """mode accepts docx."""
    assert validate(v2(mode="docx")) == []


@pytest.mark.parametrize("extra,pointer", [
    ({"snapshot_version": 4}, "/snapshot_version"),
    ({"snapshot_version": "3"}, "/snapshot_version"),
    ({"document": {"toc": "sometimes"}}, "/document/toc"),
    ({"document": {"numbering": "yes"}}, "/document/numbering"),
    ({"document": {"id": "not-a-uuid"}}, "/document/id"),
    ({"coverage_links": {"R1.1": []}}, "/coverage_links"),
    ({"coverage_links": [{"tests": []}]}, "/coverage_links/0/objective_id"),
    ({"coverage_links": [{"objective_id": "R1.1", "tests": "LangBiTe"}]}, "/coverage_links/0/tests"),
])
def test_each_new_key_is_validated(extra, pointer):
    assert pointer in pointers(validate(v2(**extra)))


@pytest.mark.parametrize("field,value", [
    ("header_text", "x" * 121), ("footer_text", "x" * 121), ("marking", "secret"), ("show_document_id", "yes"),
])
def test_the_new_style_fields_are_validated(field, value):
    """Header and footer at most 120 characters, marking in its enum, the document id flag a boolean."""
    style = dict(GOOD_V2["style"])
    style[field] = value
    assert f"/style/{field}" in pointers(validate(v2(style=style)))


def test_coverage_links_at_most_200_items():
    links = [{"objective_id": f"R{i}", "tests": [], "checklists": []} for i in range(201)]
    assert "/coverage_links" in pointers(validate(v2(coverage_links=links)))


# A lone surrogate anywhere is refused as a validation problem.

def _opts(s, n=0):
    return s["blocks"][n]["options"]


# where: (puts the lone surrogate there, the problem's pointer, the problem's instance_id: the index of
# the block it is in, None outside a block, or the escaped id itself when the id is what is broken)
SURROGATES = {
    "option": (lambda s: _opts(s).update(text="a\ud800b"), "/blocks/0/options/text", 0),
    "nested": (lambda s: _opts(s).update(extra={"list": ["ok", {"deep": "x\udfff"}]}),
               "/blocks/0/options/extra/list/1/deep", 0),
    "key": (lambda s: _opts(s).update({"k\udc00": "v"}), "/blocks/0/options/k\\udc00", 0),
    "layout_name": (lambda s: s["layout"].update(name="\ud83dname"), "/layout/name", None),
    "header": (lambda s: s["style"].update(header_text="head\udbff"), "/style/header_text", None),
    "enum_value": (lambda s: _opts(s).update(format="plain\ud800"), "/blocks/0/options/format", 0),
    "type_mismatch_in_a_list": (lambda s: s["blocks"].append(block("test_results", tools=["ok", 5, "\ud800"])),
                                "/blocks/1/options/tools/2", 1),
    "block_type": (lambda s: s["blocks"][0].update(block_type="free\ud800text"), "/blocks/0/block_type", 0),
    "top_level_key": (lambda s: s.update({"k\ud800": 1}), "/k\\ud800", None),
    "mode": (lambda s: s.update(mode="pdf\ud800"), "/mode", None),
    "coverage_links": (lambda s: s["coverage_links"][0].update(objective_id="R\ud8001"),
                       "/coverage_links/0/objective_id", None),
    "four_deep": (lambda s: _opts(s).update(x=[[[["\ud800"]]]]), "/blocks/0/options/x/0/0/0/0", 0),
    "style_font": (lambda s: s["style"].update(font="inter\ud800"), "/style/font", None),
    "document_id": (lambda s: s["document"].update(id="2222\ud800"), "/document/id", None),
    "lone_low": (lambda s: _opts(s).update(text="a\udfffb"), "/blocks/0/options/text", 0),
    "reversed_pair": (lambda s: _opts(s).update(text="a\ude00\ud83db"), "/blocks/0/options/text", 0),
    "instance_id": (lambda s: s["blocks"][0].update(instance_id="x\ud800y"), "/blocks/0/instance_id", "x\\ud800y"),
}


@pytest.mark.parametrize("where", list(SURROGATES))
def test_a_lone_surrogate_is_a_validation_problem(where):
    import copy
    import json

    put, pointer, in_block = SURROGATES[where]
    s = copy.deepcopy(v2(**GOOD_V2))
    put(s)
    problems = validate(s)
    bad = [p for p in problems if p["code"] == "invalid_snapshot" and p["pointer"] == pointer
           and p["message"] == "holds a lone surrogate"]
    assert bad, problems
    expected = in_block if in_block is None or isinstance(in_block, str) else s["blocks"][in_block]["instance_id"]
    assert bad[0]["instance_id"] == expected
    json.dumps(problems, ensure_ascii=False).encode("utf-8")  # the answer itself can be sent


def test_a_valid_surrogate_pair_is_fine():
    s = v2(**GOOD_V2)
    s["blocks"][0]["options"]["text"] = "smile \U0001F600"
    assert validate(s) == []


@pytest.mark.db
@pytest.mark.parametrize("mode", ["preview", "pdf", "docx"])
def test_render_refuses_a_lone_surrogate_cleanly(deps, mode):
    InvalidSnapshot = need("report_renderer.document", "InvalidSnapshot")
    render = need("report_renderer.document", "render")
    s = snapshot([block("free_text", text="a\ud800b")], mode=mode)
    with pytest.raises(InvalidSnapshot) as exc:
        render(s, deps)
    assert any(p["pointer"] == "/blocks/0/options/text" for p in exc.value.problems)
