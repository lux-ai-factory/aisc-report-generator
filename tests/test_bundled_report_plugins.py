"""The report add-ons in plugins/ ship with the renderer: each bundled tool is drawn by its own
renderer, not the generic table, in the tests' environment and in the image alike."""
import re
from pathlib import Path

from report_renderer.registry import build_registry

ROOT = Path(__file__).resolve().parents[1]
BUNDLED = (("LangBiTe", "langbite"), ("Promptfoo", "promptfoo"), ("StrongREJECT", "strongreject"),
           ("MLA-Reject", "mlareject"))


def test_each_bundled_tool_has_its_own_renderer():
    reg = build_registry()
    for display, name in BUNDLED:
        renderer = reg.tool_for({"display_name": display, "name": name, "package_name": f"aisc-plugin-{name}"})
        assert renderer is not None, display
        assert type(renderer).__module__.startswith(f"aisc_report_plugin_{name}"), (display, type(renderer))


def test_the_image_copies_the_add_ons_before_installing_the_locked_packages():
    dockerfile = (ROOT / "Dockerfile").read_text()
    copy = re.search(r"^COPY plugins \./plugins$", dockerfile, re.M)
    install = dockerfile.index("uv export")
    assert copy and copy.start() < install
    ignore = ROOT / ".dockerignore"
    rules = [line.strip() for line in ignore.read_text().splitlines() if line.strip() and not line.startswith("#")] if ignore.exists() else []
    assert not [r for r in rules if r.lstrip("/").startswith("plugins")], rules  # nothing hides plugins/


def test_the_build_context_leaves_out_local_environments():
    """COPY plugins would otherwise carry each folder's .venv and build leftovers into the image."""
    ignore = (ROOT / ".dockerignore").read_text().split()
    for pattern in ("**/.venv", "**/__pycache__", "**/*.egg-info", "**/build"):
        assert pattern in ignore, pattern
