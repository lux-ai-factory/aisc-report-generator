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

import asyncio
import base64
import hmac
import logging
import os
from time import perf_counter
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request, Response

import render

EXPECTED = os.environ.get("REPORT_SERVICE_TOKEN", "").encode()

#: how long the whole artifact-download phase may take before remaining charts
#: are marked unavailable; the backend's generate call waits 120 s in total, so
#: this budget leaves the rest for rendering the document.
ARTIFACT_BUDGET_SECONDS = 90.0

logger = logging.getLogger(__name__)

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
    started = perf_counter()
    await resolve_artifacts(snapshot)
    fetched = perf_counter()
    if fmt == "pdf":
        document = render.render_pdf(snapshot)
        logger.info(
            "Report timings: artifacts=%.3fs render=%.3fs",
            fetched - started,
            perf_counter() - fetched,
        )
        return Response(
            content=document,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="report.pdf"'},
        )
    if fmt == "html":
        document = render.render_html(snapshot)
        logger.info(
            "Report timings: artifacts=%.3fs render=%.3fs",
            fetched - started,
            perf_counter() - fetched,
        )
        return Response(content=document, media_type="text/html; charset=utf-8")
    return Response("unsupported format", status_code=422)


def _loggable_url(image: str) -> str:
    """The URL with any userinfo stripped, so credentials never reach the logs."""
    parts = urlsplit(image)
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    return parts._replace(netloc=netloc).geturl()


async def resolve_artifacts(snapshot):
    """Embed approved artifact PNGs, keeping healthy charts if a download fails.

    One overall timeout cancels active downloads and queued work, including
    slow response headers and bodies, leaving time for document rendering.
    """
    origin = os.environ.get("REPORT_BACKEND_INTERNAL_URL", "http://aisc-backend:8000")
    expected = urlsplit(origin)

    references = {}

    def visit(value):
        if isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            image = value.get("image", "")
            if isinstance(image, str) and image.startswith(("http://", "https://")):
                url = urlsplit(image)
                if (url.scheme, url.netloc) != (
                    expected.scheme,
                    expected.netloc,
                ) or "/report-artifacts/" not in url.path:
                    raise ValueError("Invalid report artifact URL")
                references.setdefault(image, []).append(value)
            elif isinstance(image, str) and image and not image.startswith(
                "data:image/png;base64,"
            ):
                # Only backend artifact URLs (fetched above) or PNG data URIs may be
                # embedded; anything else (raw SVG, other data URIs) is unavailable.
                value["image"] = ""
            for child in value.values():
                if isinstance(child, (dict, list)):
                    visit(child)

    visit(snapshot)

    if not references:
        return
    # Unfinished downloads stay unavailable; each completed URL updates all of
    # its references immediately, so a later timeout preserves healthy charts.
    for slots in references.values():
        for slot in slots:
            slot["image"] = ""
    if ARTIFACT_BUDGET_SECONDS <= 0:
        return

    semaphore = asyncio.Semaphore(4)
    async with httpx.AsyncClient(
        headers={"X-AISC-Service-Token": EXPECTED.decode()},
        timeout=30.0,
        follow_redirects=False,
    ) as client:
        async def fetch_image(image):
            async with semaphore:
                try:
                    async with client.stream("GET", image) as response:
                        response.raise_for_status()
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(content) + len(chunk) > 2_000_000:
                                raise ValueError("Invalid chart PNG")
                            content.extend(chunk)
                    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise ValueError("Invalid chart PNG")
                    encoded = "data:image/png;base64," + base64.b64encode(content).decode()
                    for slot in references[image]:
                        slot["image"] = encoded
                except Exception as exc:  # noqa: BLE001 - one chart must not fail the report
                    logger.warning(
                        "report artifact download failed: %s: %s", _loggable_url(image), exc
                    )

        tasks = [asyncio.create_task(fetch_image(url)) for url in references]
        try:
            async with asyncio.timeout(ARTIFACT_BUDGET_SECONDS):
                await asyncio.gather(*tasks)
        except TimeoutError:
            logger.warning("report artifact download budget exhausted")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
