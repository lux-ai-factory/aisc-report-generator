"""The source-error tile of key figures, which the seed cannot produce: an unreachable engine makes only
the tests tile "n/a (ref ...)" and the block `error`."""
import pytest

from v2_block_helpers import figure, one

pytestmark = pytest.mark.db


def test_a_source_error_makes_only_its_tile_n_a_with_a_ref(deps, monkeypatch):
    import report_renderer.data.engine as engine
    from report_renderer.errors import SourceUnavailable

    def down(*a, **k):
        raise SourceUnavailable("engine")

    monkeypatch.setattr(engine, "evaluations", down)
    _, st, node, _ = one(deps, "key_figures", figures=["version", "tests"], allow_error=True)
    assert st["status"] == "error"
    assert "n/a (ref " in figure(node, "tests")
    assert "Version 2" in figure(node, "version")
