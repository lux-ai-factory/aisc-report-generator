"""Chapter and appendix blocks: they group the following blocks.

Both read no source, so they are never empty or stale. A chapter groups every following block up
to the next chapter, the appendix or the end; everything after the appendix is the appendix part.
The document template draws their heading as an <h1 class="chapter-title">.
"""
from __future__ import annotations

from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult, richtext

from .free_text import is_placeholder


class ChapterBlock(BaseBlockRenderer):
    type_id = "chapter"
    title = "Chapter"
    contract_version = 1
    description = "Groups the following blocks under one heading."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 200, "title": "Chapter title",
                      "description": "The heading of the chapter."},
            "intro": {"type": "string", "minLength": 0, "maxLength": 5000, "title": "Introduction",
                      "description": "A few words under the chapter heading, with light formatting.",
                      "x-aisc-prose": True},
            "page_break_before": {"type": "boolean", "title": "Start on a new page",
                                  "description": "Starts the chapter on a new page in the PDF.", "x-aisc-more": True},
        },
        "required": ["title"],
    }
    default_options = {"title": "Chapter", "intro": "", "page_break_before": True}
    reads = ()
    choice_options = ()

    def load(self, ctx, options):
        return None

    def render(self, data, options, ctx):
        intro = options.get("intro") or ""
        # an introduction still holding the placeholder is treated as empty
        html = str(richtext.render(intro)) if intro.strip() and not is_placeholder(intro) else ""
        return BlockResult(html=html, status="ok")


class AppendixBlock(BaseBlockRenderer):
    type_id = "appendix"
    title = "Appendix"
    contract_version = 1
    description = "Everything after it is the appendix."
    options_schema = {"type": "object", "additionalProperties": False, "properties": {}}
    default_options = {}
    reads = ()
    choice_options = ()

    def load(self, ctx, options):
        return None

    def render(self, data, options, ctx):
        return BlockResult(html="", status="ok")
