# AISC report

The **Report** of the AI Assessment Sandbox: **one lean, backend-only microservice**. The backend
(Django) owns every piece of data and hands it here as a **JSON snapshot**
(`aisc_backend.services.report_snapshot`); this service only **draws the document** — HTML preview
or PDF (weasyprint) — from that snapshot, and reads **no database**.

Flow: webapp → Django backend → `report` (`POST /api/generate`) → document.

Structured like `apps/qualification` (src-layout, `[tool.uv] package = false`).

## Layout

The submodule holds only the lean report service (the upstream composer, DB-coupled renderer and
plugin bundles were removed in the cleanup):

```
src/
  app.py               the FastAPI server: POST /api/generate (X-AISC-Service-Token), GET /health
  render.py            draws the snapshot into HTML / PDF
  plots.py             the evaluations' declared charts -> bars
  charts.py            the bar/hbar SVG renderer (inlined from the plugin interface)
  cardgraph.py         the AI-card graph / figure -> inline SVG
  templates/report.html.j2
```

None of it imports a database; every datum arrives in the snapshot.

## Build

```sh
docker build -t aisc-report .
```

## Run

```sh
REPORT_SERVICE_TOKEN=... uvicorn app:app --host 0.0.0.0 --port 8080
```

## Endpoints

**Report service** (`src/app.py`) — every route is behind the shared `X-AISC-Service-Token`:

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/health` | Liveness: `{"status": "ok", "service": "aisc-report"}` |
| `POST` | `/api/generate` | Render a snapshot → the document bytes (`application/pdf`, or `text/html; charset=utf-8`); 401 without the token, 502 when the renderer fails |

**Backend report API** the webapp's Report page uses (`aisc_backend.routers.report`):

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/projects/{pid}/reports` | List the project's reports (the cards) |
| `POST` | `/projects/{pid}/reports/generate` | Create the report and answer immediately with `status: "pending"`; the render runs in the background and flips it to `generated`/`failed` |
| `GET`  | `/projects/{pid}/reports/{report_pid}/pdf` | Stream the stored document |
| `DELETE` | `/projects/{pid}/reports/{report_pid}` | Delete a report (editor) |
| `GET`/`PUT` | `/projects/{pid}/report-settings` | The project's report look + defaults (title, subtitle, colours, font, marking, …) |

`POST /api/generate` body: `{"project_pid": str, "format": "pdf" | "html", "snapshot": {...}}`;
the snapshot is the backend's report snapshot (project, system + AI card, controls, objectives,
evaluations, sections, and `style` — the project's customisation: report title, subtitle,
primary/accent colour). Each evaluation also carries its plugins' declared charts
(`get_metric_visualizations`) and the run's measurements; the renderer draws them as inline SVG
bars (`src/plots.py` + the plugin interface's `charts.py`). The cover also shows key-figures tiles,
and the AI system chapter draws the **webapp's system band** (system + its aspect rows, node types
visible) from `system.card.view` as static SVG scaled to one page, then the **expanded risk cards**
(Risk N · caused by / leading to / impact / affecting / controlled by / areas, VAIR terms after the
`·`) like the webapp's expanded chains, plus the AI card's aspect rows and knowledge-graph counts
and checklist answers. The backend also normalises the card's JSON-LD to plain `{nodes, edges}`
(`card.graph`) as a fallback for the figure when the view is absent. The renderer only needs
`snapshot`, `format` and the token.

## Tests

The lean renderer is verified by building the image and posting a backend-shaped snapshot to
`/api/generate` (PDF and HTML), checking that an invalid style falls back to the defaults and that a
declared chart renders as SVG in both formats (the chart renderer and the AI-card graph are pure
functions checked by ruff + a smoke render on the image).
