"""Block types and tool renderers come from the renderer itself and from installed packages only.

There is no plugin directory and no session-based `{TOOL}ReportPlugin`: a tool without a tool
renderer gets the generic table.
"""
import importlib.util
import inspect

from report_renderer import context, registry


def test_the_registry_takes_no_plugin_directories():
    assert "plugin_dirs" not in inspect.signature(registry.build_registry).parameters


def test_the_registry_has_no_session_based_plugins():
    assert not hasattr(registry.Registry, "register_legacy")
    assert importlib.util.find_spec("report_renderer.tools.legacy_adapter") is None


def test_the_environment_names_no_plugin_directory():
    assert "REPORT_PLUGIN_PATH" not in inspect.getsource(context)
    assert "REPORT_PLUGIN_PATH" not in inspect.getsource(registry)
