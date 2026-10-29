"""tests/golden/capture.py re-baselines the goldens on the same bed the suite renders them on."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)


def test_the_capture_script_imports_from_the_repository_root():
    r = _python("import runpy; runpy.run_path('tests/golden/capture.py', run_name='capture')")
    assert r.returncode == 0, r.stderr[-1500:]


def test_the_capture_script_builds_the_bed_the_suite_uses():
    r = _python("import runpy\n"
                "g = runpy.run_path('tests/golden/capture.py', run_name='capture')\n"
                "import conftest\n"
                "print(g['build_bed'] is conftest.build_bed, g['bed_sources'] is conftest.bed_sources)")
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.split() == ["True", "True"]


def test_the_capture_script_writes_where_it_is_told():
    r = _python("import inspect, runpy\n"
                "g = runpy.run_path('tests/golden/capture.py', run_name='capture')\n"
                "print(list(inspect.signature(g['main']).parameters))")
    assert r.returncode == 0, r.stderr[-1500:]
    assert "out_dir" in r.stdout
