"""Tool renderers for the registry and Test results tests."""
from aisc_report_plugin_interface import BaseToolRenderer


class LangBiTeTool(BaseToolRenderer):
    tool_names = ("LangBiTe",)

    def render(self, run, ctx):
        return "<p>LANGBITE-TOOL-OUTPUT</p>"


class BrokenLangBiTeTool(BaseToolRenderer):
    tool_names = ("LangBiTe",)

    def render(self, run, ctx):
        raise RuntimeError("LANGBITE-RENDERER-BOOM")


class FailingMysteryVerdict(BaseToolRenderer):
    tool_names = ("Mystery Tool",)

    def render(self, run, ctx):
        return "<p>MYSTERY-TOOL-OUTPUT</p>"

    def verdict(self, run):
        return "fail"
