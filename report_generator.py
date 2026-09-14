import json
from pathlib import Path
from datetime import datetime
import os
from collections import defaultdict
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from src.database_manager import DatabaseManager
from src.database_reader import DatabaseReader
from src.plugin_registry import PluginRegistry


class ReportGenerator:
    def __init__(self,
                 output_path: Path | str = "./reports",
                 filename: str = "assessment_report",
                 logo_path: Path | str = "resources/templates/logo.svg",
                 system_info_path: Path | str = None,
                 plugin_path: Path | str = None,
                    custom_report_style: str = None,
                    db_url: str = None,
                    project: str | int = None,
                          tool_plots_path: Path | str = None,
                 ):
        self.output_path = Path(output_path)
        self.filename = filename
        
        self.project = project

        if self.project is None:
            raise ValueError("A project id or name must be provided to generate a project-scoped report.")

        self.system_info = Path(system_info_path) if system_info_path else None
        self.plugin_path = Path(plugin_path) if plugin_path else Path("./plugins")
        self.tool_plots_path = Path(tool_plots_path) if tool_plots_path else None
        self.custom_report_style = custom_report_style

        # css is weird about svg file inclusion
        logo_url = str(Path(logo_path).absolute()) if logo_path else None
        self.logo_path = f"file://{logo_url}" if logo_url and not logo_url.startswith('file://') else None

        print(f"[DEBUG] Initialized ReportGenerator with output_path={self.output_path}, "
              f"filename={self.filename}, logo_path={self.logo_path}, "
              f"system_info={self.system_info}, plugin_path={self.plugin_path}, "
              f"custom_report_style={self.custom_report_style}, tool_plots_path={self.tool_plots_path}")
        
        self.db_url = db_url

    @staticmethod
    def _normalize_tool_key(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    def _load_tool_plots(self) -> dict[str, list[dict[str, str]]]:
        if self.tool_plots_path is None or not self.tool_plots_path.exists():
            return {}

        supported_suffixes = {".svg", ".png", ".jpg", ".jpeg", ".webp"}
        extension_priority = {".svg": 3, ".png": 2, ".jpg": 1, ".jpeg": 1, ".webp": 1}

        plots_by_tool: dict[str, list[dict[str, str]]] = defaultdict(list)

        for tool_dir in sorted([p for p in self.tool_plots_path.iterdir() if p.is_dir()]):
            best_files_by_stem: dict[str, Path] = {}

            for file_path in sorted(tool_dir.iterdir()):
                if not file_path.is_file() or file_path.suffix.lower() not in supported_suffixes:
                    continue

                stem = file_path.stem
                current = best_files_by_stem.get(stem)
                if current is None or extension_priority.get(file_path.suffix.lower(), 0) > extension_priority.get(current.suffix.lower(), 0):
                    best_files_by_stem[stem] = file_path

            selected_files = [best_files_by_stem[stem] for stem in sorted(best_files_by_stem.keys())]
            plot_items: list[dict[str, str]] = []

            for file_path in selected_files:
                item: dict[str, str] = {
                    "name": file_path.stem,
                    "path": file_path.resolve().as_uri(),
                }

                if file_path.suffix.lower() == ".svg":
                    try:
                        item["svg_content"] = file_path.read_text(encoding="utf-8")
                    except Exception:
                        pass

                plot_items.append(item)

            if not plot_items:
                continue

            folder_name = tool_dir.name
            alias_keys = {
                folder_name,
                folder_name.lower(),
                folder_name.upper(),
                self._normalize_tool_key(folder_name),
            }
            for alias in alias_keys:
                plots_by_tool[alias] = plot_items

        return dict(plots_by_tool)

    def run(self) -> Path:

        plugin_registry = PluginRegistry(plugin_dir=self.plugin_path)

        # establish datbase connection to read global data and data needed for orchestration, such as which plugins to load and which evaluations and tools to generate report sections for
        db_manager = DatabaseManager(self.db_url)
        db_session = db_manager.get_session()
        db_reader = DatabaseReader(db_session)

        tool_plots = self._load_tool_plots()

        
        report_sections = {}

        # load system info if provided
        if self.system_info:
            with open(self.system_info, "r") as f:
                system_info = json.load(f)
        else:
            system_info = {}

        assessment_summary = db_reader.get_summary(self.project)
        evaluations = db_reader.get_project_evaluations(self.project)
        
        for eval in evaluations:
            report_sections.update({eval.id: {}})
            tools_in_eval = db_reader.get_tools_for_evaluation(eval.id)
            for tool_id, tool_name in tools_in_eval:
                reporter_cls = plugin_registry.load(plugin_name=tool_name)
                
                # create the restricted session for the plugin and instantiate its reporter
                with db_manager.get_plugin_restricted_session(project_id=eval.project_id, evaluation_id=eval.id, tool_id=tool_id) as restricted_db_session:
                    reporter = reporter_cls(db_session=restricted_db_session)

                    content = reporter.generate_content(tool_plots=tool_plots)
                    report_sections[eval.id].update({tool_name: content})


        env = Environment(loader=FileSystemLoader("resources/templates"))
        report_template = env.get_template("report.html.j2")
        report_content = report_template.render(logo_path=self.logo_path,
                                                system_info=system_info,
                                                assessment_summary=assessment_summary,
                                                plugin_sections = report_sections,
                                                custom_report_style=self.custom_report_style
                                                )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_path.mkdir(parents=True, exist_ok=True)
        output_file = self.output_path / f"{self.filename}_{timestamp}.pdf"

        HTML(string=report_content).write_pdf(output_file)
        return output_file


if __name__ == "__main__":
    config = {
        "output_path": os.getenv("REPORT_OUTPUT_PATH", "./reports"),
        "filename": os.getenv("REPORT_FILENAME", "assessment_report"),
        "plugin_path": os.getenv("REPORT_PLUGIN_PATH"),
        "logo_path": os.getenv("REPORT_LOGO_PATH", "resources/templates/logo.svg"),
        "custom_report_style": os.getenv("REPORT_STYLE_PATH"),
        "system_info": os.getenv("REPORT_SYSTEM_INFO"),
        "project": os.getenv("PROJECT_NAME"), 
        "tool_plots_path": os.getenv("REPORT_TOOL_PLOTS_PATH") or os.getenv("TMP_PLOTS_PATH"),
    }

    generator = ReportGenerator(output_path=config["output_path"],
                                filename=config["filename"],
                                plugin_path=config["plugin_path"],
                                logo_path=config["logo_path"],
                                system_info_path=config["system_info"],
                                custom_report_style=config["custom_report_style"],
                                db_url=os.getenv("DB_URL"),
                                project=config["project"],
                                tool_plots_path=config["tool_plots_path"],
                                )
    generator.run()