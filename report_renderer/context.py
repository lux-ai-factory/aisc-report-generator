"""What a block is given: the project, the pinned version, the newer versions, the time, the mode,
and data access already scoped to that project and version."""
from __future__ import annotations

import functools
import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

from aisc_report_plugin_interface.i18n import package_language_file, translator as make_translator

from .selection import EMPTY, Selection
from . import languages
from .data import Sources
from .data import platform as platform_data
from .data.scope import NotInProject
from .data.vocab import airo_labels, objective_labels, with_own_objectives
from .errors import PlatformUnavailable, SourceUnavailable
from .registry import Registry, build_registry
from .superset import BoundedImages, NoChartData, chart_data_from_env, image_provider_from_env

DATA_MODULES = ("platform", "qualification", "control_objectives", "engine", "controls", "superset_db")


@dataclass
class Deps:
    registry: Registry
    sources: Sources
    images: object
    clock: Callable[[], datetime]
    chart_data: object | None = None
    #: (mime type, bytes) of the cover's logo
    logo: tuple[str, bytes] | None = None

    @classmethod
    def from_env(cls, env) -> "Deps":
        logo = None
        logo_path = env.get("REPORT_LOGO_PATH")
        if logo_path and Path(logo_path).is_file():
            mime = "image/svg+xml" if logo_path.lower().endswith(".svg") else "image/png"
            logo = (mime, Path(logo_path).read_bytes())
        return cls(registry=build_registry(), sources=Sources.from_env(env),
                   images=image_provider_from_env(env), chart_data=chart_data_from_env(env),
                   clock=lambda: datetime.now(timezone.utc), logo=logo)


@dataclass(frozen=True)
class ReportInfo:
    layout_id: str | None
    layout_name: str
    revision: int | None
    requested_by: str
    coverage_links: tuple
    # document options; the defaults give a plain English report
    language: str = "en"
    marking: str = "none"
    document_id: str | None = None
    toc: str = "on"
    numbering: bool = False
    header_text: str | None = None
    footer_text: str | None = None
    show_document_id: bool = False
    fingerprint: str = ""
    #: {"seq", "entry_sha256"} of the project's ledger when the report was made, or None
    ledger_anchor: dict | None = None
    #: {plugin configuration id: [chart]}: what each plugin declares (declared.py), or None
    declared_charts: dict | None = None
    # the data the report covers
    selection: Selection = EMPTY


class _Bound:
    """One data module with the project, the version and the sources already filled in."""

    def __init__(self, module, project_id, system_id, sources):
        self._module, self._p, self._s, self._sources = module, project_id, system_id, sources

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        f = getattr(self._module, name)
        return functools.partial(f, self._p, self._s, sources=self._sources)


class ScopedData:
    def __init__(self, project_id, system, newer, deps: Deps):
        self.project_id = project_id
        self.system = MappingProxyType(dict(system))
        self.system_id = system["pid"]
        self.system_number = system["number"]
        self.deps = deps
        self.newer = tuple(MappingProxyType(dict(n)) for n in newer)
        self.sources = deps.sources
        self.images = BoundedImages(deps.images, 3)
        self.chart_data = deps.chart_data if deps.chart_data is not None else NoChartData()
        self.tools = deps.registry
        self.superset_url = deps.sources.superset_url
        self.logo = deps.logo

    def __getattr__(self, name):
        """One bound accessor per data module, e.g. `ctx.data.engine.evaluations(statuses=...)`."""
        if name not in DATA_MODULES:
            raise AttributeError(name)
        module = importlib.import_module(f"report_renderer.data.{name}")
        bound = _Bound(module, self.project_id, self.system_id, self.sources)
        self.__dict__[name] = bound
        return bound

    def for_version(self, pid) -> "ScopedData":
        """Scoped data of an earlier version of the same project.

        Raises NotInProject when pid is not a version of this project numbered below the pinned one."""
        base = platform_data.pinned_system(self.project_id, pid, sources=self.sources)
        if base["project_id"] != str(self.project_id) or base["number"] >= self.system_number:
            raise NotInProject("the version to compare with is not an earlier version of this project")
        return ScopedData(self.project_id, base, (), self.deps)

    @functools.cached_property
    def vocab(self) -> dict:
        return airo_labels(self.sources.airo_vocab_path, getattr(self.sources, "vair_vocab_path", None))

    @functools.cached_property
    def objectives(self) -> dict:
        """Labels of the built-in objectives and of the project's own objectives."""
        return with_own_objectives(objective_labels(self.sources.objectives_csv_path),
                                   self.control_objectives.own_objectives())


DEFAULT_CHART_COLOURS = {"primary": "#000FDF", "text": "#000000", "grid": "#CCCCCC"}


def _english(msgid, **params) -> str:
    return make_translator()(msgid, **params)


def _english_for(package):
    return make_translator()


@dataclass(frozen=True)
class BlockContext:
    project_id: str
    project: Mapping
    system: Mapping
    newer_versions: tuple[int, ...]
    generated_at: datetime
    mode: str
    data: ScopedData
    report: ReportInfo
    # language and number formats; the defaults are English with a decimal point
    language: str = "en"
    t: Callable = _english
    translate_for: Callable = _english_for
    decimal_separator: str = "."
    percent_format: str = "{value}%"
    tool_options: dict = field(default_factory=dict)
    #: colours of charts drawn by the renderer and the tool renderers
    chart_colours: dict = field(default_factory=lambda: dict(DEFAULT_CHART_COLOURS))

    def number(self, value) -> str:
        """A number (or its already formatted text) with the report's decimal separator."""
        if value is None:
            return ""
        text = value if isinstance(value, str) else str(value)
        return text.replace(".", self.decimal_separator)

    def percent(self, share, decimals: int = 1) -> str:
        """A share 0..1 as a percentage in the report's format."""
        if share is None:
            return "n/a"
        text = f"{float(share) * 100:.{decimals}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return self.percent_format.replace("{value}", text.replace(".", self.decimal_separator))


def context_for(project_id, system_id, *, deps, mode="preview", layout=None, requested_by="",
                coverage_links=(), language="en", report=None, primary_color=None) -> BlockContext:
    try:
        system = platform_data.pinned_system(project_id, system_id, sources=deps.sources)
        project = platform_data.project(project_id, system_id, sources=deps.sources)
        newer = platform_data.newer_versions(project_id, system_id, sources=deps.sources)
    except SourceUnavailable:
        raise PlatformUnavailable("the platform database is unreachable") from None
    if project is None:
        # a project whose database is not made yet has a stand-in version; one the platform does not
        # know is not a project at all
        raise NotInProject("no such project")
    layout = layout or {}
    language = "en"  # reports are English only
    t, messages = languages.translator()
    info = ReportInfo(layout_id=layout.get("id"), layout_name=layout.get("name", ""),
                      revision=layout.get("revision"), requested_by=requested_by or "",
                      coverage_links=tuple(coverage_links or ()), language=language, **(report or {}))

    def translate_for(package):
        return make_translator(package_language_file(package, "en"), messages)

    pid = system["project_id"]
    return BlockContext(
        project_id=pid,
        project=MappingProxyType(dict(project or {})),
        system=MappingProxyType(dict(system)),
        newer_versions=tuple(n["number"] for n in newer),
        generated_at=deps.clock(),
        mode=mode,
        data=ScopedData(pid, system, newer, deps),
        report=info,
        language=language,
        t=t,
        translate_for=translate_for,
        decimal_separator=messages.decimal_separator,
        percent_format=messages.percent_format,
        chart_colours={**DEFAULT_CHART_COLOURS, **({"primary": primary_color} if primary_color else {})},
    )
