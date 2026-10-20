"""The renderer builds from this repository and the report plugin interface, which is what a recursive
clone of aisc provides. The evaluation tools' own report renderers are bundled in plugins/ (one folder
each) and installed with it, found through the `aisc_report.tools` entry point; a tool without
one gets the generic table."""
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_PLUGINS = ("aisc-report-plugin-mlareject", "aisc-report-plugin-langbite",
                "aisc-report-plugin-strongreject", "aisc-report-plugin-promptfoo")
INTERFACE_PATH = "../../shared/report-plugin-interface"   # aisc's submodule layout


def pyproject():
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_the_interface_is_a_dependency():
    assert any(d.startswith("aisc-report-plugin-interface") for d in pyproject()["project"]["dependencies"])


def test_the_bundled_tool_renderers_are_dependencies():
    deps = pyproject()["project"]["dependencies"]
    assert sorted(d for d in deps if d.startswith(TOOL_PLUGINS)) == sorted(TOOL_PLUGINS), deps


def test_the_path_sources_are_the_interface_submodule_and_the_bundled_folders():
    sources = pyproject()["tool"]["uv"]["sources"]
    assert set(sources) == {"aisc-report-plugin-interface", *TOOL_PLUGINS}, sorted(sources)
    assert sources["aisc-report-plugin-interface"]["path"] == INTERFACE_PATH
    for name in TOOL_PLUGINS:
        folder = sources[name]["path"]
        assert folder == "plugins/" + name.removeprefix("aisc-report-plugin-"), (name, folder)
        assert (ROOT / folder / "pyproject.toml").is_file(), folder


def test_the_lock_has_each_bundled_tool_renderer_from_its_folder():
    lock = (ROOT / "uv.lock").read_text()
    for name in TOOL_PLUGINS:
        assert re.search(rf'name = "{name}"\nversion = "[^"]+"\nsource = {{ directory = "plugins/', lock), name


def test_the_dockerfile_copies_only_the_interface_where_the_path_source_resolves():
    """The one build context copied in is the interface, and it lands exactly where the path source
    resolves from the WORKDIR the lock is exported in, without climbing above / (uv refuses
    "/app/../../shared": path could not be normalized)."""
    import posixpath
    dockerfile = (ROOT / "Dockerfile").read_text()
    copies = [m for m in re.findall(r"COPY\s+--from=(\S+)\s+\S+\s+(\S+)", dockerfile) if "/" not in m[0] and ":" not in m[0]]
    assert [c[0] for c in copies] == ["interface"], copies
    workdir = re.findall(r"^WORKDIR\s+(\S+)", dockerfile, re.M)[-1]
    assert len([p for p in workdir.split("/") if p]) >= INTERFACE_PATH.count(".."), workdir
    assert posixpath.normpath(posixpath.join(workdir, INTERFACE_PATH)) == copies[0][1], (workdir, copies)
