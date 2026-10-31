"""A report's look (template): font, base font size, primary and accent colour, logo.

The composer keeps templates per project and sends the chosen one in the snapshot as
`style`. The renderer checks it, applies it to the preview and the PDF, and puts the
template's logo on the cover. Without a style the report keeps the platform look.
"""
import base64

import pytest

from conftest import block, need, section, snapshot

#: A real 1x1 PNG: the logo is opened as what it says it is
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgECgFAACZAIb7eT5IAAAAAElFTkSuQmCC"


def style(**over):
    s = {"font": "liberation-serif", "font_size_pt": 11, "primary_color": "#123456", "accent_color": "#abcdef"}
    s.update(over)
    return s


def validate(s):
    return need("report_renderer.snapshot", "validate")(s)


def styled(blocks, st, **kw):
    s = snapshot(blocks, **kw)
    s["style"] = st
    return s


# The font list.

def test_the_fonts_offered_are_ones_the_pdf_can_use():
    fonts = need("report_renderer.style", "FONTS")
    ids = [f["id"] for f in fonts]
    for expected in ("inter", "liberation-sans", "liberation-serif", "dejavu-sans", "dejavu-serif", "roboto"):
        assert expected in ids
    assert all(f["label"] and f["stack"] for f in fonts)


# The snapshot's style is checked.

def test_a_good_style_has_no_problems():
    assert validate(styled([block("free_text", text="x")], style())) == []


def test_a_style_with_a_logo_has_no_problems():
    assert validate(styled([block("cover")], style(logo={"mime": "image/png", "data_base64": PNG}))) == []


def test_no_style_is_fine():
    assert validate(snapshot([block("free_text", text="x")])) == []


@pytest.mark.parametrize("over,pointer", [
    ({"font": "comic-sans"}, "/style/font"),
    ({"font_size_pt": 30}, "/style/font_size_pt"),
    ({"font_size_pt": 6}, "/style/font_size_pt"),
    ({"primary_color": "red"}, "/style/primary_color"),
    ({"accent_color": "#12345"}, "/style/accent_color"),
    ({"logo": {"mime": "application/pdf", "data_base64": PNG}}, "/style/logo/mime"),
])
def test_a_bad_style_is_refused_with_its_pointer(over, pointer):
    problems = validate(styled([block("free_text", text="x")], style(**over)))
    assert pointer in [p["pointer"] for p in problems]


# The look is applied.

def test_the_css_overrides_carry_the_template():
    css = need("report_renderer.style", "css_overrides")(style())
    assert "--l-aif-primary: #123456" in css and "--l-aif-accent: #abcdef" in css
    assert "Liberation Serif" in css and "11pt" in css


def test_no_style_means_no_overrides():
    assert need("report_renderer.style", "css_overrides")(None) == ""


def test_css_overrides_never_carry_markup():
    css = need("report_renderer.style", "css_overrides")(style(primary_color="#000000"))
    assert "<" not in css and "}" in css


@pytest.mark.db
def test_the_preview_uses_the_template(deps):
    result = need("report_renderer.document", "render")(styled([block("free_text", text="x")], style()), deps)
    assert "--l-aif-primary: #123456" in result["html"]
    assert "Liberation Serif" in result["html"]


@pytest.mark.db
def test_the_templates_logo_is_on_the_cover(deps):
    b = block("cover")
    result = need("report_renderer.document", "render")(
        styled([b], style(logo={"mime": "image/png", "data_base64": PNG})), deps)
    node = section(result["html"], b["instance_id"])
    img = node.find("img")
    assert img is not None and img["src"] == f"data:image/png;base64,{PNG}"



# The logo is what it says it is: the renderer opened any bytes with Pillow, which reads PSD, EPS,
# JPEG 2000 and FITS whatever the declared type, and a bad base64 crashed the render (500) instead of
# being a problem.

def _logo_problems(data_base64, mime="image/png"):
    s = styled([block("cover")], style(logo={"mime": mime, "data_base64": data_base64}))
    return [p["pointer"] for p in validate(s)]


def test_a_logo_that_is_not_base64_is_a_problem():
    assert _logo_problems("!!!") == ["/style/logo/data_base64"]


def test_a_logo_whose_content_is_not_its_type_is_a_problem():
    import io

    from PIL import Image

    jpeg = io.BytesIO()
    Image.new("RGB", (1, 1)).save(jpeg, "JPEG")
    assert _logo_problems(base64.b64encode(jpeg.getvalue()).decode()) == ["/style/logo/data_base64"]
    assert _logo_problems(base64.b64encode(b"8BPS" + b"\x00" * 40).decode()) == ["/style/logo/data_base64"]
    assert _logo_problems(base64.b64encode(b"not an svg").decode(), mime="image/svg+xml") == ["/style/logo/data_base64"]


def test_a_logo_past_the_pixel_cap_is_a_problem(monkeypatch):
    import io

    from PIL import Image

    import report_renderer.style as style_module
    monkeypatch.setattr(style_module, "LOGO_MAX_PIXELS", 100)
    big = io.BytesIO()
    Image.new("RGB", (20, 20)).save(big, "PNG")
    assert _logo_problems(base64.b64encode(big.getvalue()).decode()) == ["/style/logo/data_base64"]


def test_a_real_svg_logo_has_no_problem():
    svg = base64.b64encode(b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>')
    assert _logo_problems(svg.decode(), mime="image/svg+xml") == []


# An SVG logo is capped by the size it declares, like a raster logo by its pixels: a 101-byte SVG
# declaring 16000 x 16000 px became a 32000 x 32000 picture (3.8 GiB) in the Word export.

def _svg(attrs):
    return base64.b64encode(f'<svg xmlns="http://www.w3.org/2000/svg" {attrs}><rect width="100%" height="100%"'
                            f' fill="#123456"/></svg>'.encode()).decode()


def test_an_svg_logo_declaring_a_huge_size_is_a_problem():
    assert _logo_problems(_svg('width="16000" height="16000"'), mime="image/svg+xml") == ["/style/logo/data_base64"]
    s = styled([block("cover")], style(logo={"mime": "image/svg+xml", "data_base64": _svg('width="16000" height="16000"')}))
    assert "more than 16000000 pixels" in validate(s)[0]["message"]


def test_an_svg_logo_sized_by_a_huge_viewbox_or_units_is_a_problem():
    assert _logo_problems(_svg('viewBox="0 0 16000 16000"'), mime="image/svg+xml") == ["/style/logo/data_base64"]
    assert _logo_problems(_svg('width="200in" height="200in"'), mime="image/svg+xml") == ["/style/logo/data_base64"]


def test_an_svg_logo_with_no_size_at_all_is_a_problem():
    assert _logo_problems(_svg(""), mime="image/svg+xml") == ["/style/logo/data_base64"]
    assert _logo_problems(_svg('width="nan" height="10"'), mime="image/svg+xml") == ["/style/logo/data_base64"]


def test_an_svg_logo_of_a_normal_size_has_no_problem():
    assert _logo_problems(_svg('width="200" height="80"'), mime="image/svg+xml") == []
    assert _logo_problems(_svg('viewBox="0 0 200 80"'), mime="image/svg+xml") == []
    assert _logo_problems(_svg('width="60mm" height="20mm"'), mime="image/svg+xml") == []
    assert _logo_problems(_svg('width="100%" height="100%" viewBox="0 0 200 80"'), mime="image/svg+xml") == []


# An SVG logo may not carry a picture of its own: the cap above reads only the
# size the root declares, so a 200 x 100 SVG holding <image href="data:image/png;base64,..."> of a
# 12000 x 12000 PNG passed it, and drawing it took 0.7 GB in cairosvg and 1.3 GB in WeasyPrint.
# A logo needs no embedded or linked resource, so any <image>, <feImage>, <foreignObject> or href is refused.

def _png_b64(side=4):
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("1", (side, side)).save(out, "PNG")
    return base64.b64encode(out.getvalue()).decode()


def _svg_body(body, root='width="200" height="100"'):
    return base64.b64encode(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
                            f' {root}>{body}</svg>'.encode()).decode()


def test_an_svg_logo_with_an_embedded_raster_is_a_problem():
    probe = _svg_body(f'<image width="200" height="100" xlink:href="data:image/png;base64,{_png_b64()}"/>')
    assert _logo_problems(probe, mime="image/svg+xml") == ["/style/logo/data_base64"]
    s = styled([block("cover")], style(logo={"mime": "image/svg+xml", "data_base64": probe}))
    assert "embedded or linked" in validate(s)[0]["message"]


def test_an_svg_logo_with_any_image_filter_foreign_object_or_href_is_a_problem():
    png = _png_b64()
    for body in (f'<image href="data:image/png;base64,{png}" width="1" height="1"/>',
                 f'<svg:image xmlns:svg="http://www.w3.org/2000/svg" href="data:image/png;base64,{png}"/>',
                 f'<filter id="f"><feImage href="data:image/png;base64,{png}"/></filter>',
                 '<foreignObject width="10" height="10"><div xmlns="http://www.w3.org/1999/xhtml">x</div></foreignObject>',
                 '<rect id="r" width="1" height="1"/><use xlink:href="#r"/>',
                 '<a href="https://example.org"><rect width="1" height="1"/></a>'):
        assert _logo_problems(_svg_body(body), mime="image/svg+xml") == ["/style/logo/data_base64"], body


def test_an_svg_logo_of_shapes_and_text_has_no_problem():
    body = ('<defs><linearGradient id="g"><stop offset="0" stop-color="#123456"/></linearGradient></defs>'
            '<rect width="200" height="100" fill="url(#g)"/><text x="10" y="50">AISC</text>')
    assert _logo_problems(_svg_body(body), mime="image/svg+xml") == []


def _raster_b64(fmt, side=1):
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (side, side)).save(out, fmt)
    return base64.b64encode(out.getvalue()).decode()


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


#: Logos and whether the renderer refuses them, as (name, mime, data_base64, refused). The renderer's
#: POST /v1/style/check answers from the same rule, so tests/test_style_check_route.py runs this table too.
LOGOS = [
    ("not base64", "image/png", "!!!", True),
    ("a PNG", "image/png", _png_b64(), False),
    ("a JPEG", "image/jpeg", _raster_b64("JPEG"), False),
    ("a JPEG saved as a PNG", "image/png", _raster_b64("JPEG"), True),
    ("a PSD saved as a PNG", "image/png", _b64(b"8BPS" + b"\x00" * 40), True),
    ("text saved as an SVG", "image/svg+xml", _b64(b"not an svg"), True),
    ("an SVG with an XML declaration", "image/svg+xml",
     _b64(b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'), False),
    ("an SVG declaring 16000 x 16000 px", "image/svg+xml", _svg('width="16000" height="16000"'), True),
    ("an SVG with a huge viewBox", "image/svg+xml", _svg('viewBox="0 0 16000 16000"'), True),
    ("an SVG 200 inches square", "image/svg+xml", _svg('width="200in" height="200in"'), True),
    ("an SVG with no size", "image/svg+xml", _svg(""), True),
    ("an SVG whose width is nan", "image/svg+xml", _svg('width="nan" height="10"'), True),
    ("an SVG 200 x 80 px", "image/svg+xml", _svg('width="200" height="80"'), False),
    ("an SVG sized by its viewBox", "image/svg+xml", _svg('viewBox="0 0 200 80"'), False),
    ("an SVG in mm", "image/svg+xml", _svg('width="60mm" height="20mm"'), False),
    ("an SVG at 100% with a viewBox", "image/svg+xml", _svg('width="100%" height="100%" viewBox="0 0 200 80"'),
     False),
    ("an SVG holding a PNG", "image/svg+xml",
     _svg_body(f'<image width="200" height="100" xlink:href="data:image/png;base64,{_png_b64()}"/>'), True),
    ("an SVG with a feImage", "image/svg+xml",
     _svg_body(f'<filter id="f"><feImage href="data:image/png;base64,{_png_b64()}"/></filter>'), True),
    ("an SVG with a foreignObject", "image/svg+xml",
     _svg_body('<foreignObject width="10" height="10"><div xmlns="http://www.w3.org/1999/xhtml">x</div>'
               '</foreignObject>'), True),
    ("an SVG with a use href", "image/svg+xml", _svg_body('<rect id="r" width="1" height="1"/><use xlink:href="#r"/>'),
     True),
    ("an SVG of shapes and text", "image/svg+xml",
     _svg_body('<defs><linearGradient id="g"><stop offset="0" stop-color="#123456"/></linearGradient></defs>'
               '<rect width="200" height="100" fill="url(#g)"/><text x="10" y="50">AISC</text>'), False),
]


@pytest.mark.parametrize("mime,data_base64,refused", [c[1:] for c in LOGOS], ids=[c[0] for c in LOGOS])
def test_the_logo_table(mime, data_base64, refused):
    assert _logo_problems(data_base64, mime=mime) == (["/style/logo/data_base64"] if refused else [])
