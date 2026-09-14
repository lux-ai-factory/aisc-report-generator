import importlib
import inspect
import logging
import sys
from pathlib import Path
from typing import Dict

from vera_report_plugin_interface.base_report_plugin import BaseReporterPlugin




logger = logging.getLogger(__name__)
DEFAULT_PLUGIN_PATH = "plugins"


def find_plugin_package_directory(pkg_root: Path) -> Path | None:
    """
    Discover plugin root package using plugin metadata/class export contract:
    1. pkg_root/__init__.py 
    2. pkg_root/src/<module_name>/__init__.py
    3. pkg_root/<module_name>/__init__.py

    Report plugins are then discovered from classes exported by that package's
    __init__.py, based on BaseReporterPlugin inheritance.
    """
    if (pkg_root / "__init__.py").exists():
        return pkg_root

    src_dir = pkg_root / "src"
    if src_dir.exists() and src_dir.is_dir():
        for module_dir in src_dir.iterdir():
            if module_dir.is_dir() and (module_dir / "__init__.py").exists():
                return module_dir

    for module_dir in pkg_root.iterdir():
        if module_dir.is_dir() and module_dir.name != "src" and (module_dir / "__init__.py").exists():
            return module_dir

    return None


class PluginRegistry:
    def __init__(self, plugin_dir: Path | str = DEFAULT_PLUGIN_PATH):
        self.plugin_dir = Path(plugin_dir)
        self.plugins: Dict[str, type[BaseReporterPlugin]] = {}
        self._find_plugins()

    def _find_plugins(self):
        self.plugins = {}

        if not self.plugin_dir.exists() or not self.plugin_dir.is_dir():
            return

        for pkg_root in self.plugin_dir.iterdir():
            if not pkg_root.is_dir():
                continue

            module_path = find_plugin_package_directory(pkg_root)
            if not module_path:
                continue

            parent_path = str(module_path.parent)
            if parent_path not in sys.path:
                sys.path.insert(0, parent_path)

            module_name = module_path.name
            try:
                if module_name in sys.modules:
                    modules_to_remove = [
                        module
                        for module in sys.modules
                        if module == module_name or module.startswith(f"{module_name}.")
                    ]
                    for module in modules_to_remove:
                        del sys.modules[module]

                imported_module = importlib.import_module(module_name)

                for _, obj in inspect.getmembers(imported_module, inspect.isclass):
                    if issubclass(obj, BaseReporterPlugin) and obj is not BaseReporterPlugin:
                        self.plugins[obj.__name__] = obj

            except Exception as error:
                logger.error(
                    f"Failed to load report plugin module {module_name} from {pkg_root}: {error}"
                )

            loaded_from_module = [
                name
                for name, plugin_class in self.plugins.items()
                if plugin_class.__module__.split(".")[0] == module_name
                and plugin_class.__module__ in sys.modules
            ]

    def list_plugins(self) -> Dict[str, type[BaseReporterPlugin]]:
        self._find_plugins()
        return self.plugins

    def load(self, plugin_name: str) -> BaseReporterPlugin:
        self._find_plugins()

        plugin_name_normalized = _normalize_plugin_name(plugin_name)
        reporter = self.plugins.get(plugin_name_normalized + "ReportPlugin")

        if not reporter:
            raise ValueError(f"Plugin '{plugin_name}' not found in registry. Available plugins: {list(self.plugins.keys())}")

        return reporter
    
@staticmethod
def _normalize_plugin_name(name: str) -> str:
    return name.upper().replace(" ", "").replace("-", "").replace("_", "")