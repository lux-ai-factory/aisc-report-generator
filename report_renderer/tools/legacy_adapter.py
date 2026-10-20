"""A legacy `{KEY}ReportPlugin` called as a tool renderer.

Not a BaseToolRenderer on purpose: a real tool renderer wins over a legacy plugin.
"""
from __future__ import annotations


class LegacyToolAdapter:
    def __init__(self, cls):
        self.cls = cls

    def render(self, run, ctx) -> str:
        html = self.cls(db_session=None).generate_content(run=run, tool_plots={})
        if not isinstance(html, str) or html.startswith("[ERROR]"):
            raise RuntimeError(f"the legacy plugin {self.cls.__name__} failed")
        return html

    def verdict(self, run):
        return None
