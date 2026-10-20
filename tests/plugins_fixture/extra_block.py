"""An extra block renderer, as an installed package would ship one."""
from aisc_report_plugin_interface import BaseBlockRenderer, BlockResult


class ExtraBlock(BaseBlockRenderer):
    type_id = "extra_block"
    title = "Extra"
    contract_version = 1
    options_schema = {"type": "object", "properties": {}}
    default_options = {}
    reads = ()

    def load(self, ctx, options):
        return None

    def render(self, data, options, ctx):
        return BlockResult(html="<p>EXTRA-BLOCK-OUTPUT</p>", status="ok")


class CoverAgain(ExtraBlock):
    """Claims a built-in type id: the renderer must refuse to start."""
    type_id = "cover"
