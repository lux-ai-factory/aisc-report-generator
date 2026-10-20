"""Packaging of the MLA-Reject plugin."""
import subprocess
import sys
from importlib import metadata


def _python(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd="/")


# A package that fails to import is skipped by the renderer, so it must import cleanly
def test_the_package_imports_without_the_old_generator_model():
    r = _python("import aisc_report_plugin_mlareject, sys; print('resources' in sys.modules)")
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.strip() == "False"


def test_importing_prints_nothing():
    r = _python("import aisc_report_plugin_mlareject")
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout == ""


def test_both_plugins_are_exported():
    r = _python("from aisc_report_plugin_mlareject import MLAREJECTToolRenderer, MLAREJECTReportPlugin")
    assert r.returncode == 0, r.stderr[-1500:]


# The legacy plugin keeps its name and its session contract; with no session it raises
def test_the_legacy_plugin_without_a_session_raises():
    r = _python(
        "from aisc_report_plugin_mlareject import MLAREJECTReportPlugin\n"
        "try:\n"
        "    MLAREJECTReportPlugin(db_session=None).generate_content(run=None, tool_plots={})\n"
        "    print('no error')\n"
        "except Exception as e:\n"
        "    print(type(e).__name__)\n")
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.strip() not in ("", "no error")


def test_the_installed_distribution_advertises_it():
    found = [ep for ep in metadata.entry_points(group="aisc_report.tools")
             if ep.value == "aisc_report_plugin_mlareject:MLAREJECTToolRenderer"]
    assert len(found) == 1
