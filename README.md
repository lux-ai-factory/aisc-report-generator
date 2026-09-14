# VERA Report Generator

Generates a PDF assessment report from database results, system metadata JSON, shared templates, and tool-specific report plugins.

## How the report generator works

The main entrypoint is `report_generator.py` (`ReportGenerator.run()`).

At runtime, it performs the following workflow:

```mermaid
flowchart TD
	A[Start ReportGenerator.run] --> B[Load plugins via PluginRegistry]
	B --> C[Open global DB session]
	C --> D[Load optional system_info JSON]
	D --> E[Load optional tool plots]
	E --> F[Fetch project summary + evaluations]
	F --> G{For each evaluation}
	G --> H[Resolve tools in evaluation]
	H --> I{For each tool}
	I --> J[Load matching plugin class]
	J --> K[Open restricted plugin DB session]
	K --> L[Instantiate plugin]
	L --> M[Generate plugin HTML content]
	M --> I
	I --> N[Collect plugin_sections]
	N --> G
	G --> O[Render report HTML via Jinja2]
	O --> P[Write timestamped PDF via WeasyPrint]
	P --> Q[Return output path]
```

1. **Initialize plugin registry**
	 - Scans the plugin root directory (default: `./plugins`) and discovers reporter classes that inherit from `BaseReporterPlugin`.

2. **Open database sessions**
	 - Creates a global read-only session for orchestration-level queries (project summary, evaluation list, tools per evaluation).
	 - Creates per-plugin **restricted** sessions scoped to:
		 - `project_id`
		 - `evaluation_id`
		 - `tool_id`
	 - This enforces plugin data isolation.

3. **Load optional assets**
	 - `system_info` JSON (if provided).
	 - Optional plot files from `tool_plots_path` (grouped by tool folder).

4. **Build report sections by evaluation and tool**
	 - For each evaluation in the selected project:
		 - Resolve tools used in that evaluation.
		 - Load the matching plugin class from the registry.
		 - Instantiate plugin with restricted DB session.
		 - Call `plugin.generate_content(tool_plots=...)`.
	 - Plugin HTML snippets are collected into `plugin_sections`.

5. **Render final HTML and export PDF**
	 - Renders `resources/templates/report.html.j2` with Jinja2.
	 - Uses WeasyPrint to write a timestamped PDF to `output_path`.

---

## Expected inputs

## Required runtime inputs

- **Database URL** (`DB_URL`): SQLAlchemy-compatible database URL.
- **Project selector** (`PROJECT_NAME`): project name or project id (required).

If `PROJECT_NAME` is missing, generation fails with a `ValueError`.

## Optional runtime inputs (environment variables)

- `REPORT_OUTPUT_PATH` (default: `./reports`)
- `REPORT_FILENAME` (default: `assessment_report`)
- `REPORT_PLUGIN_PATH` (default: `./plugins`)
- `REPORT_LOGO_PATH` (default: `resources/templates/logo.svg`)
- `REPORT_STYLE_PATH` (optional custom CSS included by Jinja)
- `REPORT_SYSTEM_INFO` (optional JSON metadata file)
- `REPORT_TOOL_PLOTS_PATH` or `TMP_PLOTS_PATH` (optional directory for plot assets)

## System metadata JSON

When `REPORT_SYSTEM_INFO` is provided, it should point to a JSON file like examples in `resources/example/`.

## Plot directory shape

If plots are provided, expected layout is:

```text
<tool_plots_path>/
	<tool_name_or_alias>/
		figure_1.svg
		figure_2.png
```

Supported formats: `.svg`, `.png`, `.jpg`, `.jpeg`, `.webp`.

Plots are attached to plugins by matching tool keys (case/format variants and normalized names).

## Database entities used by orchestration

The generator reads project/evaluation/tool structure from SQLAlchemy models in `resources/sql_alchemy.py`, especially:
- `Project`
- `Evaluation`
- `Observation`
- `Tool`
- `LegalRequirement`

---

## Local usage

## Install

Python >= 3.12 is required.

```bash
pip install -e .
```

## Run

```bash
DB_URL='postgresql+psycopg://user:pass@host:5432/dbname' \
PROJECT_NAME='my_project' \
REPORT_SYSTEM_INFO='resources/example/covenance_system_info.json' \
REPORT_TOOL_PLOTS_PATH='resources/example/tmp_plots' \
python report_generator.py
```

The PDF is written to `REPORT_OUTPUT_PATH` (default `./reports`) with a timestamped filename.
