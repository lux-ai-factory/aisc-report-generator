"""Packaging of the MLA-Reject plugin."""
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def test_only_the_tool_renderer_is_exported():
    r = _python("import aisc_report_plugin_mlareject as m; print(m.__all__)")
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.strip() == "['MLAREJECTToolRenderer']"


# The renderer hands the plugin its data: the package reads no database
def test_the_package_imports_no_database_library():
    r = _python("import aisc_report_plugin_mlareject, sys; "
                "print(sorted(m for m in sys.modules if m.split('.')[0] in ('sqlalchemy', 'psycopg', 'psycopg2')))")
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.strip() == "[]"


def test_no_database_dependency():
    deps = " ".join(tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]).lower()
    for db in ("sqlalchemy", "psycopg"):
        assert db not in deps


def test_only_the_tool_renderer_template_ships():
    names = sorted(p.name for p in (ROOT / "aisc_report_plugin_mlareject" / "templates").glob("*.j2"))
    assert names == ["tool_section.html.j2"]


def test_the_installed_distribution_advertises_it():
    found = [ep for ep in metadata.entry_points(group="aisc_report.tools")
             if ep.value == "aisc_report_plugin_mlareject:MLAREJECTToolRenderer"]
    assert len(found) == 1
