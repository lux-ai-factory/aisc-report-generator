"""Packaging of the strongreject tool renderer: its entry point, files and dependencies.

The package mirrors aisc-report-mlareject: templates under templates/*.j2, catalogues under
i18n/*.json, no database access, no import-time side effects.
"""
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

from conftest import need

ROOT = Path(__file__).resolve().parents[1]
PKG = "aisc_report_plugin_strongreject"
CLASS = "STRONGREJECTToolRenderer"
EP = f"{PKG}:{CLASS}"


def _python(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd="/")


def _package_dir() -> Path:
    d = ROOT / PKG
    if not (d / "__init__.py").exists():
        pytest.fail(f"missing feature: package {PKG}", pytrace=False)
    return d


# r_v2_16
def test_the_installed_distribution_advertises_a_tool_renderer():
    found = [ep for ep in metadata.entry_points(group="aisc_report.tools") if ep.value == EP]
    assert len(found) == 1, "missing feature: installed entry point"
    Base = need("aisc_report_plugin_interface", "BaseToolRenderer")
    assert issubclass(found[0].load(), Base)


def test_imports_cleanly_prints_nothing_no_database():
    _package_dir()
    r = _python(f"import {PKG}, sys; print(sorted(m for m in sys.modules if m.split('.')[0] in "
                "('sqlalchemy', 'psycopg', 'psycopg2', 'resources')))")
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.strip() == "[]"
    r = _python(f"import {PKG}")
    assert r.stdout == "" and r.stderr == ""


def test_no_database_dependency():
    _package_dir()
    deps = " ".join(tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]).lower()
    for db in ("sqlalchemy", "psycopg"):
        assert db not in deps


def test_the_lock_file_pins_no_database_library():
    names = {p["name"] for p in tomllib.loads((ROOT / "uv.lock").read_text())["package"]}
    assert not names & {"sqlalchemy", "psycopg", "psycopg2"}


def test_templates_and_catalogues_ship_with_the_package():
    d = _package_dir()
    assert list((d / "templates").glob("*.j2")), "missing feature: templates/*.j2"
    assert not (d / "i18n" / "fr.json").exists(), "reports are English only: i18n/fr.json must go"
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"].get("package-data", {})
    globs = " ".join(data.get(PKG, []))
    assert "templates/*.j2" in globs and "i18n/*.json" in globs
