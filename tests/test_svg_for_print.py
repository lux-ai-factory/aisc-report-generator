"""A saved plot is drawn by the PDF engine, which reads two things of an SVG differently from a browser: a text's halo
(paint-order) and the room its text takes (another font). The plot is prepared for print without changing what it
shows. No database."""
import re

from report_renderer.svg_print import for_print

LABEL = ('<text dominant-baseline="central" text-anchor="middle" style="font-size:12px;font-family:sans-serif;" y="-6" '
         'transform="translate(274 134.863)" fill="#333" stroke="rgb(255,255,255)" stroke-width="2" '
         'paint-order="stroke" stroke-miterlimit="2">55%</text>')
SVG = ('<svg width="548" height="491" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 548 491"><rect width="548" '
       'height="491" fill="none"/>' + LABEL + '<text x="30" y="7" fill="#333">Local back-end</text></svg>')


def test_a_haloed_label_is_drawn_as_its_halo_then_its_text():
    out = for_print(SVG)
    texts = re.findall(r"<text[^>]*>55%</text>", out)
    assert len(texts) == 2
    halo, text = texts
    assert 'fill="none"' in halo and 'stroke="rgb(255,255,255)"' in halo
    assert 'stroke=' not in text and 'fill="#333"' in text and "paint-order" not in text


def test_text_without_a_halo_is_left_as_it_is():
    assert '<text x="30" y="7" fill="#333">Local back-end</text>' in for_print(SVG)


def test_text_is_set_in_the_browsers_family_and_gets_room_at_the_sides():
    out = for_print(SVG)
    assert 'viewBox="-27.4 0 602.8 491"' in out and 'width="602.8"' in out
    assert "font-family:Inter, sans-serif" in out


def test_anything_else_is_untouched():
    assert '<rect width="548" height="491" fill="none"/>' in for_print(SVG)


def test_an_svg_without_a_viewbox_still_gets_room():
    out = for_print('<svg width="100" height="50" xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>')
    assert 'viewBox="-5 0 110 50"' in out and 'width="110"' in out
