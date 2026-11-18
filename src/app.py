"""The report microservice (apps/report): one lean FastAPI server.

The backend owns every piece of data (Django) and hands it here as a JSON snapshot
(aisc_backend/services/report_snapshot.py); this service only draws the document — HTML preview or
PDF — from that snapshot and reads no database itself. The snapshot is the format the backend's
`report_service` client already sends.

    POST /api/generate   {"project_pid": str, "format": "pdf" | "html", "snapshot": {...}}
    GET  /health

Every route needs the shared service token in the X-AISC-Service-Token header.
"""
from __future__ import annotations

import hmac
import os

from fastapi import FastAPI, Request, Response

import render

EXPECTED = os.environ.get("REPORT_SERVICE_TOKEN", "").encode()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def check_token(request: Request, call_next):
    given = request.headers.get("X-AISC-Service-Token", "").encode()
    if not EXPECTED or not hmac.compare_digest(given, EXPECTED):
        return Response("unauthorized", status_code=401)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "service": "aisc-report"}


@app.post("/api/generate")
async def generate(request: Request):
    body = await request.json()
    fmt = (body or {}).get("format") or "pdf"
    snapshot = (body or {}).get("snapshot") or {}
    if fmt == "pdf":
        return Response(content=render.render_pdf(snapshot), media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="report.pdf"'})
    if fmt == "html":
        return Response(content=render.render_html(snapshot), media_type="text/html; charset=utf-8")
    return Response("unsupported format", status_code=422)
