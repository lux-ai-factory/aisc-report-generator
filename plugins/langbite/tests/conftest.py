"""Shared helpers of the tool renderer tests.

`need(module, name)` fetches a public name and FAILS the test (never errors it) with
"missing feature: ..." while the name is not written yet, a missing module included.
`ctx(...)` is the block context a tool renderer receives, reduced to what the contract promises:
`tool_options`, `language`, and `translate_for(package)`.
"""
import importlib
import re
from types import SimpleNamespace

import pytest

I = "aisc_report_plugin_interface"


def need(module: str, name: str | None = None):
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name and (exc.name == module or module.startswith(exc.name + ".")):
            pytest.fail(f"missing feature: module {module}", pytrace=False)
        raise
    if name is None:
        return mod
    value = getattr(mod, name, None)
    if value is None:
        pytest.fail(f"missing feature: {module}.{name}", pytrace=False)
    return value


def _english(msgid, **params):
    return re.sub(r"\{(\w+)\}", lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0), msgid)


def ctx(show_charts=True, detail="full", language="en", translate_for=None):
    return SimpleNamespace(tool_options={"show_charts": show_charts, "detail": detail}, language=language,
                           t=_english, translate_for=translate_for or (lambda package: _english))


def soup(html: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


def text(node) -> str:
    return " ".join(node.get_text(" ").split())


def table_with(html: str, header: str):
    """The first <table> whose header row has a cell starting with `header`, as rows of cell texts."""
    for t in soup(html).find_all("table"):
        heads = [text(th) for th in t.find_all("th")]
        if any(h.startswith(header) for h in heads):
            rows = []
            for tr in t.find_all("tr"):
                cells = [text(td) for td in tr.find_all("td")]
                if cells:
                    rows.append(cells)
            return heads, rows
    return None, None


def charts_in(html: str) -> list:
    return soup(html).find_all("svg", attrs={"role": "img"})
