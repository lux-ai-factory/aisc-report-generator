# AISC report renderer

The report renderer turns a report layout into one document: HTML for the preview, PDF or DOCX for the
generated report. It is the back end of the Report in step 4 Collect evidence of AISC, the AI Assessment Sandbox
Configurator (steps: 1 Qualify the AI system, 2 Set control objectives, 3 Choose tests and checklists,
4 Collect evidence). It runs as the compose service `report-renderer` and is called only by the report composer
(`report-composer`, `apps/report-composer` in the aisc repository).

The composer sends the renderer a request: the layout, the AI card version and the selection, the coverage
links, the declared charts and the style. The renderer reads the project's data itself, as the read-only
database role `report_ro`, and draws the document. It never writes to a database or to disk. For the whole
picture, see `docs/architecture.md` in the aisc repository; for the Report from the user's side,
`docs/appendices/4-collect-evidence.md`.

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

- `report_service.py` is the HTTP interface. Every route needs the shared token in the `X-Report-Token` header
  (401 otherwise).
- The request is called the **snapshot** in the code. Version 3 is the only one the renderer takes. Its keys are
  listed under [The snapshot](#the-snapshot).
- Each block is drawn by the class registered for its type, with data scoped to the project and the chosen AI
  card version (`report_renderer/context.py`). A block reports a status: `ok`, `empty` (no data for the
  version), `stale` (newer data exists for a later version) or `error` (an error box with a reference; the
  traceback goes to the log only).
- Every project has its own database `project_<pid without hyphens>`. The project's versions (`project.system`)
  and each module's data (qualification, control objectives, engine, controls, evidence) are read there; a
  missing database, schema or table reads as empty.
- Runs on a local model file are never in a report: the run, result and dashboard chart blocks leave them out.
- The PDF is made with WeasyPrint (70 or later; Pillow 12.3 or later decodes the images) and fetches nothing but
  `data:` URIs. The DOCX is made from the same HTML with python-docx. The composer asks for the PDF copy of a
  Word report as a second render of the same snapshot. The image runs as the user `renderer`, not root.
- Superset's token is renewed when it expires (a 401 logs in again). Whether a project's database exists is
  remembered for 30 seconds, so a report does not ask the platform database on every read.

### Blocks and tool renderers

Built-in block types (`report_renderer/blocks/`): cover, ai_card, risk_classification, control_objectives,
test_results, test_runs, control_answers, dashboard_chart, summary_coverage, free_text, chapter, appendix,
chart, key_figures, changes_since. The composer groups them as AI card, Control objectives and checklists,
Tests run, Results, Summary and Document; a block type from a plugin goes under Other.

- Control objectives rates each risk "Not rated" until both its impact and its likelihood are set, as step 2
  does, and marks the priority objectives with their score.
- Summary and coverage lists each objective with its linked tests and checklists (the snapshot's
  `coverage_links`), its coverage, and who reviewed the Evidence map.
- Test results names each run's target, the AI system or one component of its AI card ("Target: Scoring model
  (Model), card v2"; "Target: not recorded" for a run without one).
- Test runs lists the runs with their tools, times and configuration name. A configuration's settings are never
  read: they may hold credentials, and `report_ro` may not read them.

More block types come from installed packages (entry-point group `aisc_report.blocks`). Inside Test results,
each test tool is drawn by its **tool renderer** (entry-point group `aisc_report.tools`), or by a generic table
of its measurements. The tool renderers of LangBiTe, MLA-Reject, Promptfoo and StrongREJECT are bundled in
`plugins/<tool>/`, each a package with its own tests, and installed with the renderer; any other tool gets the
generic table. For the tools listed in `report_renderer/declared.py` (LangBiTe and Data Drift), Test results
also draws the charts the plugin declares, from the snapshot's `declared_charts`. The plugin contracts live in `aisc-report-plugin-interface`
(`shared/report-plugin-interface` in the aisc repository).

## Run it

### Inside the AISC stack (the usual way)

From the aisc folder:

```bash
uv run scripts/aisc.py start
```

This makes the secrets if they are missing (`REPORT_RO_PASSWORD`, `REPORT_SERVICE_TOKEN` and the others) and
brings up the whole stack, keeping port 443 answering on an https install.

`report-renderer` in `docker-compose.development.yml` is built from this submodule plus
`shared/report-plugin-interface` (build context `interface`). It listens on port 8001 on the backend network only
(it is not in the Caddyfile) and starts after `report-grants`, which grants `report_ro` read access to what the
report reads. It mounts three read-only data files from other modules:
`apps/qualification/src/data/airo_vocab.json`, `apps/qualification/src/data/vair_vocab.json` and
`apps/control-objectives/src/aisc_control_objectives/data/ai_act_control_objectives.csv`.

To rebuild only the renderer after a change, run `uv run scripts/aisc.py secrets`. It prints this install's exact
compose command, which ends in `up -d`. Append `--build report-renderer` to it.

### Standalone, for development

Prerequisites: Python 3.12 or later, [uv](https://docs.astral.sh/uv/) (0.9 or later), the WeasyPrint system
libraries (Pango, Cairo, HarfBuzz; the Dockerfile lists the Debian packages), and Docker for the database tests.
The checkout must sit inside the aisc repository, because `pyproject.toml` takes the plugin interface from
`../../shared/report-plugin-interface`.

```bash
cd apps/report-generator
uv sync --extra dev
REPORT_SERVICE_TOKEN=... REPORT_PLATFORM_DATABASE_URL=... REPORT_SUPERSET_DATABASE_URL=... \
REPORT_PROJECT_DB_URL=... REPORT_AIRO_VOCAB_PATH=... REPORT_OBJECTIVES_CSV_PATH=... \
  uv run uvicorn report_service:app --port 8001
```

The service refuses to start without `REPORT_SERVICE_TOKEN` or any of the required settings below.

## Reference

### Settings

| variable | meaning | default | value in the stack |
|---|---|---|---|
| `REPORT_SERVICE_TOKEN` | the token shared with the composer, expected in `X-Report-Token` | required | from `env.secrets` |
| `REPORT_PLATFORM_DATABASE_URL` | the platform database, as `report_ro`; read for `core.project` and `pg_database` only | required | `report_ro` on `postgres:5432/platform` |
| `REPORT_SUPERSET_DATABASE_URL` | the dashboard's (Superset's) database, as `report_ro` | required | `report_ro` on `postgres:5432/superset` |
| `REPORT_PROJECT_DB_URL` | a project database DSN with `{database}` in place of the name; `{database}` becomes `project_<hex>` | required | `report_ro` on `postgres:5432/{database}` |
| `REPORT_AIRO_VOCAB_PATH` | the qualification's `airo_vocab.json` (labels of affected parties and impact areas) | required | `/data/airo_vocab.json` |
| `REPORT_OBJECTIVES_CSV_PATH` | the AI Act control objectives CSV (labels of the objectives) | required | `/data/ai_act_control_objectives.csv` |
| `REPORT_VAIR_VOCAB_PATH` | the qualification's generated `vair_vocab.json` (labels of VAIR terms) | unset: a term shows as its id | `/data/vair_vocab.json` |
| `REPORT_CHART_IMAGES` | `superset` turns Superset chart screenshots on; any other value leaves them off | off | `off` |
| `REPORT_SUPERSET_URL` | Superset's API, for screenshots and chart data (required when `REPORT_CHART_IMAGES=superset`) | unset | unset |
| `REPORT_SUPERSET_USER` | the Superset login for screenshots and chart data | `aisc-report` for screenshots; chart data needs it set | unset |
| `REPORT_SUPERSET_PASSWORD` | that login's password | empty | unset |
| `REPORT_SUPERSET_PUBLIC_URL` | the link base of "Open in the dashboard" | `REPORT_SUPERSET_URL` | the dashboard's address (`http://localhost:8188` by default) |
| `REPORT_LOGO_PATH` | an SVG or PNG logo for the cover (a template's own logo wins) | none | unset |
| `REPORT_RENDER_MAX_BYTES` | the largest `/v1/render` body, in bytes (413 above it) | 8388608 (8 MiB) | unset |
| `REPORT_RENDER_CONCURRENCY` | renders at once; one more is 503 `busy` | 4 | unset |

`REPORT_RO_PASSWORD` is made in `env.secrets` and reaches Compose through `env.runtime`.

### Routes

| route | what it does |
|---|---|
| `GET /health` | status, block types, tool renderers, plugin interface version, languages |
| `GET /v1/block-types` | every block type: id, title, contract version, options schema, default options, sources read, description |
| `GET /v1/fonts` | the fonts a template may choose (those installed in the image) |
| `POST /v1/choices` | `{project_id, system_id, block_type}`: the values the block's reference options may take |
| `POST /v1/render` | a snapshot: `{"html", "fingerprint", "block_statuses"}` in preview mode, `{"pdf_base64" or "docx_base64", "sha256", "fingerprint", "block_statuses"}` in pdf or docx mode; 422 with `problems` for a bad snapshot, 404 when the version is not of the project, 503 when the platform database is unreachable; 413 for a body over `REPORT_RENDER_MAX_BYTES`, 503 `busy` when `REPORT_RENDER_CONCURRENCY` renders are already running |

### The snapshot

The schema is in `report_renderer/snapshot.py`.

- Required: `project_id`, `system_id` (the AI card version), `layout` (id, name, revision), `blocks` (the ordered
  blocks with their options) and `mode` (`preview`, `pdf` or `docx`).
- Optional:
  - `style`: font, size, colours, logo, header and footer texts, marking;
  - `document`: id, table of contents, numbering, ledger anchor;
  - `coverage_links`: per objective, the linked tests and checklists of the Evidence map;
  - `declared_charts`: the charts each test plugin declares, per plugin configuration;
  - `selection`: `period_from` and `period_to` (ISO date-times with a time zone, the end excluded),
    `other_versions` (include runs made against other versions, each marked with its version; coverage still
    counts only the chosen version's runs as evidence) and `compare_to` (the version Changes since compares with;
    the previous one when null).
- `validate()` also checks what the schema cannot say. A logo must be base64 of the PNG, JPEG or SVG its mime
  names. A raster one is opened as that format only, at most 16 million pixels. An SVG one must declare a width
  and height or a viewBox; at twice that size it may not pass 16 million pixels (so 2000 x 2000 declared px at
  most), and it may hold no picture or link of its own: no `<image>`, `<feImage>`, `<foreignObject>` or href. The
  periods must be zoned date-times. The limits are the constants `LOGO_MAX_PIXELS`, `SVG_RASTER_SCALE` and
  `SVG_RASTER_MAX_SIDE` in `report_renderer/style.py`. The Word export draws an SVG (logo or chart) at twice its
  size, but never with a side over 2000 px.
- A project the platform does not know is a 404.

### Files

| path | contents |
|---|---|
| `report_service.py` | the FastAPI app and its routes |
| `report_renderer/document.py`, `snapshot.py`, `structure.py`, `style.py` | snapshot checks, document assembly, chapters and table of contents, the template's look |
| `report_renderer/context.py`, `registry.py` | what a block is given; the block types and tool renderers found |
| `report_renderer/blocks/` | the built-in blocks and their Jinja templates |
| `report_renderer/data/` | every database read, scoped to the project and version |
| `report_renderer/tools/` | the generic results table |
| `report_renderer/pdf.py`, `docx.py` | PDF (WeasyPrint) and DOCX (python-docx) output |
| `report_renderer/templates/`, `i18n/en.json` | the document template, the CSS, the English texts |
| `plugins/` | the bundled tool renderers: `langbite`, `mlareject`, `promptfoo`, `strongreject` |
| `tests/` | the tests, the golden files and a plugin fixture |

## Tests

```bash
cd apps/report-generator
env -u DATABASE_URL -u PLATFORM_TEST_DATABASE_URL uv run --extra dev pytest -q -p no:cacheprovider tests
```

Each bundled tool renderer has its own tests: `cd plugins/<tool> && uv run --extra dev pytest -q`.

Tests marked `db` need a database. They build their own throwaway Postgres bed with Docker (`postgres:15-alpine`
containers named `aisc-t-renderer-*` and `aisc-t-iso-R-renderer-*`, on a port the kernel picks) through
`scripts/lib/report_bed.py` and `scripts/lib/report_bed_isolated.py` of the aisc repository, and remove them at
the end. As a submodule of aisc the tests find that repository two folders up; elsewhere, set
`AISC_INSTALL_DIR` to an aisc checkout. Docker must be running.

The tests need the report plugin interface from `shared/report-plugin-interface` and the test beds of the aisc
repository, both only in a full aisc checkout. So the CI (`.github/workflows/ci.yml`) checks out aisc's
`pilot` around this commit and runs the command above, with `--locked`, in it; locally, run it in
a full aisc checkout.

**Never point the tests at the live database** (port 5432 of the running stack). The bed refuses to start when a
DSN variable (`DATABASE_URL`, `REPORT_PLATFORM_DATABASE_URL` and the like) is set to anything but the bed, which
is why the command above unsets them.

The golden files in `tests/golden/` hold rendered output. The CSS under `report_renderer/templates/` is copied
into every document, so even a change to a CSS comment changes the output and fails the golden tests.

## Contributing

- `pilot` is the only branch to work on; the aisc repository pins this submodule on it.
- The renderer reads the other modules' tables; it has no migrations of its own. When a module's schema
  changes, update the queries in `report_renderer/data/` and the report bed in aisc's `scripts/lib/`.
- New read access for `report_ro` goes in aisc's `init/report-ro-grants.sql`, applied by the `report-grants`
  service.
