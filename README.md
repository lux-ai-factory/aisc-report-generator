# AISC report renderer

The report renderer turns a saved report layout into one document: HTML for the preview, PDF or DOCX
for the generated report. It is part of AISC, the AI Assessment Sandbox Configurator, whose steps are
1 Qualify the AI system, 2 Set control objectives, 3 Choose tests and checklists and 4 Collect
evidence. This repository is the back end of step 4's Report: the report composer (`apps/report-composer` in the aisc repository) lets a user assemble a
layout from blocks, then sends the renderer a **snapshot** of it, and the renderer reads the project's
data and draws the document. The renderer only reads: it never writes to a database or to disk.

## How it works

```
report composer --HTTP + X-Report-Token--> report_service.py (FastAPI, port 8001)
                                             |
                                             v
                                   report_renderer.document.render(snapshot)
                                             |  each block, in layout order
                                             v
          report_renderer/blocks/*  ---reads--->  report_renderer/data/*  (as role report_ro)
                                                    platform database: core.project, pg_database
                                                    project_<hex> database: versions + module data
                                                    superset database: charts and their comments (deleted ones left out)
```

- `report_service.py` is the HTTP interface. Every route needs the shared token in the
  `X-Report-Token` header (401 otherwise).
- A **snapshot** names the project, the pinned system version (`system_id`), the layout's name and
  revision, the ordered blocks with their options, and the mode (`preview`, `pdf` or `docx`).
  Optional keys: `style` (font, size, colours, logo, header and footer texts, marking), `document`
  (id, table of contents, numbering, ledger anchor), `coverage_links`, and `selection`:
  `period_from` and `period_to` (ISO date-times with a time zone, the end excluded), `other_versions`
  (include runs made against other versions, each marked with its version; coverage still counts only
  the pinned version's runs as evidence) and `compare_to` (the version Changes since compares with; the
  previous one when null). The schema is in `report_renderer/snapshot.py`; `validate()` also checks
  what it can't say: a logo must be base64 of the PNG, JPEG or SVG its mime names (a raster one is
  opened as that format only, at most 16 million pixels; an SVG one must declare a width and height or
  a viewBox, and at twice that size it may not pass 16 million pixels, so 2000 x 2000 declared px at
  most, and it may hold no picture or link of its own: no `<image>`, `<feImage>`, `<foreignObject>` or
  href), and the periods must be zoned date-times. The limits are the constants `LOGO_MAX_PIXELS`,
  `SVG_RASTER_SCALE` and `SVG_RASTER_MAX_SIDE` in `report_renderer/style.py`. The Word export draws an
  SVG (logo or chart) at twice its size, but never with a side over 2000 px. A project the platform
  does not know is a 404.
- Each block is rendered by the class registered for its type, with data scoped to the project and
  the pinned version (`report_renderer/context.py`). A block reports a status: `ok`, `empty` (no data
  for the version), `stale` (newer data exists for a later version) or `error` (an error box with a
  reference; the traceback goes to the log only).
- Every project has its own database `project_<pid without hyphens>`. The project's versions
  (`project.system`) and each module's data (qualification, control objectives, engine, controls) are
  read there; a missing database, schema or table reads as empty.
- The PDF is made with WeasyPrint (70 or later; Pillow 12.3 or later decodes the images) and fetches
  nothing but `data:` URIs. The DOCX is made from the same HTML with python-docx. The image runs as the
  user `renderer`, not root.
- Superset's token is renewed when it expires (a 401 logs in again). Whether a project's database exists
  is remembered for 30 seconds, so a report does not ask the platform database on every read.

### Routes

| route | what it does |
|---|---|
| `GET /health` | status, block types, tool renderers, plugin interface version, languages |
| `GET /v1/block-types` | every block type: id, title, contract version, options schema, default options, sources read, description |
| `GET /v1/fonts` | the fonts a template may choose (those installed in the image) |
| `POST /v1/choices` | `{project_id, system_id, block_type}`: the values the block's reference options may take |
| `POST /v1/render` | a snapshot: `{"html", "fingerprint", "block_statuses"}` in preview mode, `{"pdf_base64" or "docx_base64", "sha256", "fingerprint", "block_statuses"}` in pdf or docx mode; 422 with `problems` for a bad snapshot, 404 when the version is not of the project, 503 when the platform database is unreachable; 413 for a body over `REPORT_RENDER_MAX_BYTES`, 503 `busy` when `REPORT_RENDER_CONCURRENCY` renders are already running |

### Blocks and plugins

Built-in block types (`report_renderer/blocks/`): cover, ai_card, risk_classification,
control_objectives, test_results, test_runs, control_answers, dashboard_chart, summary_coverage,
free_text, chapter, appendix, chart, key_figures, changes_since.

- Test results names each run's target, the AI system or one component of its AI card
  ("Target: Scoring model (Model), card v2"; "Target: not recorded" for a run made before targets).
- Test runs lists the runs with their tools, times and configuration name. A configuration's settings
  are never read: they may hold credentials, and `report_ro` may not read them.

More block types come from installed packages (entry-point group `aisc_report.blocks`) or from the
plugin directories in `REPORT_PLUGIN_PATH`. Inside Test results, each test tool is drawn by its
**tool renderer** (entry-point group `aisc_report.tools`), by a legacy `{TOOL}ReportPlugin` found in
the plugin directories, or by a generic table of its measurements. The tool renderers of LangBiTe,
MLA-Reject, Promptfoo and StrongREJECT are bundled in `plugins/<tool>/` (each a package with its own
tests: `cd plugins/<tool> && uv run --extra dev pytest -q`) and installed with the renderer; any other
tool gets the generic table. The plugin contracts live in `aisc-report-plugin-interface`
(`shared/report-plugin-interface` in aisc).

## Install and run

### Inside the AISC stack (the usual way)

The compose service is `report-renderer` in `docker-compose.development.yml` of the aisc repository.
It is built from this submodule plus `shared/report-plugin-interface`, listens on port 8001 on the
backend network only (it is not in the Caddyfile) and is called by `report-composer`. It starts after
`report-grants`, which grants `report_ro` read access to what the report reads.

From the aisc repository root:

```bash
./scripts/secrets.sh        # once: makes REPORT_RO_PASSWORD, REPORT_SERVICE_TOKEN and the other secrets
docker compose -p aisc --env-file env.runtime -f docker-compose.plugin_downloader.yml \
  -f docker-compose-infra.development.yml -f docker-compose.development.yml up -d --build
```

This brings up the whole stack. To rebuild only the renderer after a change, add `report-renderer` at
the end of the same command. The service mounts three read-only data files from other modules:
`apps/qualification/src/data/airo_vocab.json`, `apps/qualification/src/data/vair_vocab.json` and
`apps/control-objectives/src/aisc_control_objectives/data/ai_act_control_objectives.csv`.

### Standalone, for development

Prerequisites: Python 3.12 or later, [uv](https://docs.astral.sh/uv/) (0.9 or later), the WeasyPrint
system libraries (Pango, Cairo, HarfBuzz; the Dockerfile lists the Debian packages), and Docker for the
database tests. The checkout must sit inside the aisc repository, because `pyproject.toml` takes the
plugin interface from `../../shared/report-plugin-interface`.

```bash
cd apps/report-generator
uv sync --extra dev
REPORT_SERVICE_TOKEN=... REPORT_PLATFORM_DATABASE_URL=... REPORT_SUPERSET_DATABASE_URL=... \
REPORT_PROJECT_DB_URL=... REPORT_AIRO_VOCAB_PATH=... REPORT_OBJECTIVES_CSV_PATH=... \
  uv run uvicorn report_service:app --port 8001
```

The service refuses to start without `REPORT_SERVICE_TOKEN` or any of the required variables below.

## Configuration

| variable | meaning | default |
|---|---|---|
| `REPORT_SERVICE_TOKEN` | the token shared with the composer, expected in `X-Report-Token` | required |
| `REPORT_PLATFORM_DATABASE_URL` | the platform database, as the read-only role `report_ro`; read for `core.project` and `pg_database` only | required |
| `REPORT_SUPERSET_DATABASE_URL` | the dashboard's (Superset's) database, as `report_ro` | required |
| `REPORT_PROJECT_DB_URL` | a project database DSN with `{database}` in place of the name; `{database}` becomes `project_<hex>` | required |
| `REPORT_AIRO_VOCAB_PATH` | the qualification's `airo_vocab.json` (labels of affected parties and impact areas) | required |
| `REPORT_OBJECTIVES_CSV_PATH` | the AI Act control objectives CSV (labels of the objectives) | required |
| `REPORT_VAIR_VOCAB_PATH` | the qualification's generated `vair_vocab.json` (labels of VAIR terms) | unset: a term shows as its id |
| `REPORT_CHART_IMAGES` | `superset` turns Superset chart screenshots on; any other value leaves them off | off |
| `REPORT_SUPERSET_URL` | Superset's API, for screenshots and chart data (required when `REPORT_CHART_IMAGES=superset`) | unset |
| `REPORT_SUPERSET_USER` | the Superset login for screenshots and chart data | `aisc-report` for screenshots; chart data needs it set |
| `REPORT_SUPERSET_PASSWORD` | that login's password | empty |
| `REPORT_SUPERSET_PUBLIC_URL` | the link base of "Open in the dashboard" | `REPORT_SUPERSET_URL` |
| `REPORT_PLUGIN_PATH` | plugin directories, separated by `:` | none |
| `REPORT_LOGO_PATH` | an SVG or PNG logo for the cover (a template's own logo wins) | none |
| `REPORT_RENDER_MAX_BYTES` | the largest `/v1/render` body, in bytes (413 above it) | 8388608 (8 MiB) |
| `REPORT_RENDER_CONCURRENCY` | renders at once; one more is 503 `busy` | 4 |

In the stack, the database URLs use `report_ro` with `REPORT_RO_PASSWORD` from `env.runtime`, and
`REPORT_CHART_IMAGES` is `off`.

## Tests

```bash
cd apps/report-generator
env -u DATABASE_URL -u PLATFORM_TEST_DATABASE_URL uv run --extra dev pytest -q -p no:cacheprovider tests
```

Tests marked `db` need a database. They build their own throwaway Postgres bed with Docker
(`postgres:15-alpine` containers named `aisc-t-renderer-*` and `aisc-t-iso-R-renderer-*`, on a port the
kernel picks) through `scripts/lib/report_bed.py` and `scripts/lib/report_bed_isolated.py` of the aisc
repository, and remove them at the end. As a submodule of aisc the tests find that repository two
folders up; elsewhere, set `AISC_INSTALL_DIR` to an aisc checkout. Docker must be running.

There is no CI of its own: the tests need the report plugin interface from `shared/report-plugin-interface`
and the test beds of the aisc repository, both only in a full aisc checkout. Run them there.

**Never point the tests at the live database** (port 5432 of the running stack). The bed refuses to
start when a DSN variable (`DATABASE_URL`, `REPORT_PLATFORM_DATABASE_URL` and the like) is set to
anything but the bed, which is why the command above unsets them.

The golden files in `tests/golden/` hold rendered output. The CSS under `report_renderer/templates/` is
copied into every document, so even a change to a CSS comment changes the output and fails the golden
tests.

## Layout

| path | contents |
|---|---|
| `report_service.py` | the FastAPI app and its routes |
| `report_renderer/document.py`, `snapshot.py`, `structure.py`, `style.py` | snapshot checks, document assembly, chapters and table of contents, the template's look |
| `report_renderer/context.py`, `registry.py` | what a block is given; the block types and tool renderers found |
| `report_renderer/blocks/` | the built-in blocks and their Jinja templates |
| `report_renderer/data/` | every database read, scoped to the project and version |
| `report_renderer/tools/` | the generic results table and the legacy plugin adapter |
| `report_renderer/pdf.py`, `docx.py` | PDF (WeasyPrint) and DOCX (python-docx) output |
| `report_renderer/templates/`, `i18n/en.json` | the document template, the CSS, the English texts |
| `tests/` | the tests, the golden files and a plugin fixture |

## Contributing

- `feat/unified-modules` is the only branch to work on; the aisc repository pins this submodule on it.
- The renderer reads the other modules' tables; it has no migrations of its own. When a module's
  schema changes, update the queries in `report_renderer/data/` and the report bed in aisc's
  `scripts/lib/`.
- New read access for `report_ro` goes in aisc's `init/report-ro-grants.sql`, applied by the
  `report-grants` service.
