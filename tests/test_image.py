"""What the renderer's image runs as and on: the image ran as root, and
Pillow 12.1.1 and WeasyPrint 68.1 had advisories reachable or near-reachable from a template logo."""
import re
from importlib.metadata import version
from pathlib import Path

DOCKERFILE = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()


def _at_least(name, minimum):
    have = tuple((int(x) for x in re.findall(r"\d+", version(name))[:3]))
    have = have + (0,) * (3 - len(have))
    return have >= minimum, version(name)


def test_the_renderer_runs_as_a_user_of_its_own_not_root():
    users = re.findall(r"^USER\s+(\S+)", DOCKERFILE, re.M)
    assert users and users[-1] not in ("root", "0")


def test_pillow_and_weasyprint_carry_the_fixes():
    ok, have = _at_least("pillow", (12, 3, 0))
    assert ok, have                     # CVE-2026-42311, -59203, -59204, -40192
    ok, have = _at_least("weasyprint", (70, 0, 0))
    assert ok, have                     # GHSA-jf6q-chmf-3h3v
