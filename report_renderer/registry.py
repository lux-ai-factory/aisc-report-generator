"""The block types and tool renderers the renderer knows.

Built-in blocks first, then installed packages (entry-point groups `aisc_report.blocks` and
`aisc_report.tools`), then the plugin directories (REPORT_PLUGIN_PATH). A package that fails to
import is skipped with a warning; two declarations of one block type or two renderers of one
tool refuse to start.
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import inspect
import logging
import sys
from collections.abc import Mapping
from pathlib import Path

from aisc_report_plugin_interface import (BaseBlockRenderer, BaseReporterPlugin, BaseToolRenderer,
                                          normalise_tool_name, tool_keys)

from .tools.legacy_adapter import LegacyToolAdapter

logger = logging.getLogger("report_renderer.registry")

BLOCKS_GROUP = "aisc_report.blocks"
TOOLS_GROUP = "aisc_report.tools"
#: tool renderers of contract 1 and 2 load; a higher one is skipped with a warning
MAX_TOOL_CONTRACT = 2


class DuplicateBlockType(RuntimeError):
    """Two classes declare the same block type."""


class DuplicateToolRenderer(RuntimeError):
    """Two renderers claim the same tool."""


def _legacy_key(cls) -> str:
    name = cls.__name__
    if name.endswith("ReportPlugin"):
        name = name[: -len("ReportPlugin")]
    return normalise_tool_name(name)


class Registry:
    def __init__(self):
        self._blocks: dict[str, tuple[type, str]] = {}
        self._tools: list[tuple[type, set[str], str]] = []
        self._legacy: dict[str, tuple[type, str]] = {}

    def register_block(self, cls, origin: str) -> None:
        cls.validate_declaration()
        if cls.type_id in self._blocks:
            first = self._blocks[cls.type_id][1]
            message = f"block type {cls.type_id!r} is declared twice: by {first} and by {origin}"
            logger.error(message)
            raise DuplicateBlockType(message)
        self._blocks[cls.type_id] = (cls, origin)

    def register_tool(self, cls, origin: str) -> None:
        version = getattr(cls, "contract_version", 1)
        if not isinstance(version, int) or version > MAX_TOOL_CONTRACT:
            logger.warning("tool renderer %s needs a newer report renderer", origin)
            return
        keys = {normalise_tool_name(n) for n in cls.tool_names}
        for other, other_keys, other_origin in self._tools:
            if keys & other_keys:
                message = (f"tool {', '.join(sorted(keys & other_keys))} has two renderers: "
                           f"{other_origin} and {origin}")
                logger.error(message)
                raise DuplicateToolRenderer(message)
        self._tools.append((cls, keys, origin))

    def register_legacy(self, cls, origin: str) -> None:
        key = _legacy_key(cls)
        if key in self._legacy:
            message = f"tool {key} has two legacy report plugins: {self._legacy[key][1]} and {origin}"
            logger.error(message)
            raise DuplicateToolRenderer(message)
        self._legacy[key] = (cls, origin)

    def block(self, type_id):
        entry = self._blocks.get(type_id)
        return entry[0] if entry else None

    def block_types(self) -> list[type]:
        return [cls for cls, _ in self._blocks.values()]

    def tool_for(self, plugin_row: Mapping):
        keys = tool_keys(plugin_row.get("display_name"), plugin_row.get("name"), plugin_row.get("package_name"))
        for cls, cls_keys, _ in self._tools:
            if cls_keys & keys:
                return cls()
        for key, (cls, _) in self._legacy.items():
            if key in keys:
                return LegacyToolAdapter(cls)
        return None

    def tool_renderers(self) -> list[type]:
        """The registered tool renderer classes, in registration order (read only)."""
        return [cls for cls, _, _ in self._tools]

    def tool_names(self) -> list[str]:
        names = [n for cls, _, _ in self._tools for n in cls.tool_names]
        return names + [key for key in self._legacy]


def _register_class(reg: Registry, obj, origin: str) -> None:
    if not inspect.isclass(obj):
        return
    if issubclass(obj, BaseBlockRenderer) and obj is not BaseBlockRenderer and not inspect.isabstract(obj):
        reg.register_block(obj, origin)
    elif issubclass(obj, BaseToolRenderer) and obj is not BaseToolRenderer and not inspect.isabstract(obj):
        reg.register_tool(obj, origin)
    elif (issubclass(obj, BaseReporterPlugin) and obj is not BaseReporterPlugin
          and obj.__name__.endswith("ReportPlugin")):
        reg.register_legacy(obj, origin)


def _load_entry_points(reg: Registry, entry_points) -> None:
    for ep in entry_points:
        try:
            obj = ep.load()
        except Exception as exc:  # a broken package is skipped, never fatal
            logger.warning("skipping report plugin %s: %s", ep.value, exc)
            continue
        if ep.group == BLOCKS_GROUP:
            reg.register_block(obj, ep.value)
        elif ep.group == TOOLS_GROUP:
            reg.register_tool(obj, ep.value)


def _import_path(path: Path, index: int):
    name = f"report_plugin_{index}_{path.stem}"
    if path.is_dir():
        spec = importlib.util.spec_from_file_location(name, path / "__init__.py",
                                                      submodule_search_locations=[str(path)])
    else:
        spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


_counter = iter(range(10**9))


def _load_plugin_dirs(reg: Registry, plugin_dirs) -> None:
    for d in plugin_dirs:
        d = Path(d)
        if not d.is_dir():
            logger.warning("skipping report plugin directory %s: not a directory", d)
            continue
        candidates = sorted(p for p in d.iterdir()
                            if (p.is_file() and p.suffix == ".py" and p.name != "__init__.py")
                            or (p.is_dir() and (p / "__init__.py").is_file()))
        for path in candidates:
            try:
                module = _import_path(path, next(_counter))
            except Exception as exc:
                logger.warning("skipping report plugin %s: %s", path, exc)
                continue
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if obj.__module__ == module.__name__:
                    _register_class(reg, obj, str(path))


def build_registry(builtins=True, entry_points=None, plugin_dirs=()) -> Registry:
    reg = Registry()
    if builtins:
        from .blocks import BUILTIN_BLOCKS

        for cls in BUILTIN_BLOCKS:
            reg.register_block(cls, cls.__module__)
    if entry_points is None:
        entry_points = list(importlib.metadata.entry_points(group=BLOCKS_GROUP)) + \
            list(importlib.metadata.entry_points(group=TOOLS_GROUP))
    _load_entry_points(reg, entry_points)
    _load_plugin_dirs(reg, plugin_dirs)
    return reg
