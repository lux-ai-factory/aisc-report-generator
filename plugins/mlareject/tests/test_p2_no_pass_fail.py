"""MLA-Reject writes scores per case, never a pass or fail,
so its section shows none and is unchanged. A compatibility guard: it passes today and must keep passing."""
import re

from test_tool_renderer import renderer, run


def test_no_pass_or_fail_word_and_no_verdict():
    html = renderer().render(run(), ctx=None)
    assert "Mean score" in html
    assert not re.search(r"\b(pass|passed|fail|failed)\b", re.sub(r"<[^>]+>", " ", html), re.I)
    assert renderer().verdict(run()) is None
