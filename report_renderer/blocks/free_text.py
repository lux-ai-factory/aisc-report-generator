"""The Free text block."""
from __future__ import annotations

import re

from markupsafe import Markup, escape
from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult, richtext

#: the text the composer puts in a prose option that is still to be written
PLACEHOLDER = "Write this section."


def is_placeholder(text) -> bool:
    """True when a text is still the unwritten placeholder (trimmed)."""
    return isinstance(text, str) and text.strip() == PLACEHOLDER


class FreeTextBlock(BaseBlockRenderer):
    type_id = "free_text"
    title = "Free text"
    contract_version = 2
    description = "Your own text, with light formatting."
    options_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "text": {"type": "string", "minLength": 1, "maxLength": 20000, "title": "Text",
                     "description": "The text of this section.", "x-aisc-prose": True},
            "format": {"enum": ["plain", "markdown"], "title": "Format", "description": "Plain text or light formatting.",
                       "x-aisc-enum-labels": {"plain": "Plain text", "markdown": "Light formatting"},
                       "x-aisc-more": True},
        },
        "required": ["text"],
    }
    default_options = {"format": "plain"}
    #: new free text blocks use light formatting; a stored block without a format stays plain
    new_instance_options = {"format": "markdown"}
    reads = ()
    choice_options = ()

    def load(self, ctx, options):
        return None

    def render(self, data, options, ctx):
        """Plain text: a blank line starts a paragraph, a newline is a line break.
        With format markdown, light formatting."""
        if options.get("format") == "markdown":
            html = Markup('<div class="free-text">') + richtext.render(options["text"]) + Markup("</div>")
            return BlockResult(html=str(html), status="ok")
        paragraphs = [Markup("<br>").join(escape(line) for line in para.split("\n"))
                      for para in re.split(r"\n\s*\n", options["text"].strip()) if para.strip()]
        html = self.render_package_template("templates/free_text.html.j2", paragraphs=paragraphs)
        return BlockResult(html=html, status="ok")
