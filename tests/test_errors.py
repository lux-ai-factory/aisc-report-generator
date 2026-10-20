"""Error references and logs."""
import re

from conftest import need


def test_an_error_ref_is_8_hex_characters():
    new_error_ref = need("report_renderer.errors", "new_error_ref")
    refs = {new_error_ref() for _ in range(200)}
    assert all(re.fullmatch(r"[0-9a-f]{8}", r) for r in refs)
    assert len(refs) > 190  # random, not a counter
