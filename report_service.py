"""The renderer's HTTP interface. Its only caller is the report composer.

Every route needs the shared token in X-Report-Token (compared in constant time). The routes:
GET /health, GET /v1/block-types, GET /v1/fonts, POST /v1/style/check, POST /v1/choices,
POST /v1/render.
Nothing is written to disk,
and no log line carries the token or a database address.

A render is bounded: a body over REPORT_RENDER_MAX_BYTES is 413 before it is parsed, and when
REPORT_RENDER_CONCURRENCY renders are already running a further one is 503 at once.

    uvicorn report_service:app --host 0.0.0.0 --port 8001
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import threading

from fastapi import Body, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

import aisc_report_plugin_interface

from report_renderer import languages
from report_renderer.context import Deps, context_for
from report_renderer.data.scope import NotInProject
from report_renderer.document import InvalidSnapshot, NotFound, render
from report_renderer import style
from report_renderer.errors import PlatformUnavailable, new_error_ref

logger = logging.getLogger("report_service")


def _error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


#: a snapshot is small: blocks, options and at most one logo of 1.4 MB in base64
DEFAULT_RENDER_MAX_BYTES = 8 * 1024 * 1024
#: a PDF render takes a CPU and some hundred MB: a few at once, the rest are told to come back
DEFAULT_RENDER_CONCURRENCY = 4


def _positive_int(env, name: str, default: int) -> int:
    raw = env.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a whole number, not {raw!r}") from None
    if value < 1:
        raise RuntimeError(f"{name} must be at least 1")
    return value


def render_limits(env) -> tuple[int, int]:
    """(largest render body in bytes, renders at once), from REPORT_RENDER_MAX_BYTES and
    REPORT_RENDER_CONCURRENCY; a value that is not a positive whole number stops the start."""
    return (_positive_int(env, "REPORT_RENDER_MAX_BYTES", DEFAULT_RENDER_MAX_BYTES),
            _positive_int(env, "REPORT_RENDER_CONCURRENCY", DEFAULT_RENDER_CONCURRENCY))


async def _body_within(request: Request, limit: int) -> bytes | None:
    """The request body, or None as soon as it is longer than limit (Content-Length or bytes read)."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        return None
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            return None
    return bytes(body)


def create_app(deps=None, token=None, max_body_bytes=None, max_concurrent_renders=None) -> FastAPI:
    token = token if token is not None else os.environ.get("REPORT_SERVICE_TOKEN", "")
    if not token:
        raise RuntimeError("REPORT_SERVICE_TOKEN is not set")
    env_bytes, env_slots = render_limits(os.environ)
    max_body_bytes = max_body_bytes or env_bytes
    slots = threading.BoundedSemaphore(max_concurrent_renders or env_slots)
    deps = deps or Deps.from_env(os.environ)
    expected = token.encode()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def check_token(request: Request, call_next):
        given = request.headers.get("x-report-token", "").encode()
        if not hmac.compare_digest(given, expected):
            return _error(401, "unauthorized", "A valid X-Report-Token header is required.")
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok", "block_types": [c.type_id for c in deps.registry.block_types()],
                "tool_renderers": deps.registry.tool_names(),
                "interface_version": aisc_report_plugin_interface.INTERFACE_VERSION,
                "languages": languages.languages()}

    @app.get("/v1/block-types")
    def block_types():
        return [{"type_id": c.type_id, "title": c.title, "contract_version": c.contract_version,
                 "options_schema": c.full_options_schema(), "default_options": c.full_default_options(),
                 "reads": list(c.reads), "description": getattr(c, "description", "") or "",
                 "new_instance_options": dict(getattr(c, "new_instance_options", {}) or {})}
                for c in deps.registry.block_types()]

    @app.get("/v1/fonts")
    def fonts():
        return [{"id": f["id"], "label": f["label"]} for f in style.FONTS]

    @app.post("/v1/style/check")
    async def style_check(request: Request):
        """Whether a template's logo can be used: the composer asks before saving one, so the rule
        lives here once. The body is a snapshot's `style`; the answer is why not, or null."""
        body = await _body_within(request, max_body_bytes)
        if body is None:
            return _error(413, "too_large", f"A style may be at most {max_body_bytes} bytes.")
        try:
            given = json.loads(body)
        except ValueError:
            given = None
        if not isinstance(given, dict):
            return _error(422, "invalid_style", "The body must be a JSON object.")
        return {"problem": await run_in_threadpool(style.logo_problem, given)}

    @app.post("/v1/choices")
    def choices(body: dict = Body(...)):
        cls = deps.registry.block(body.get("block_type"))
        if cls is None:
            return _error(404, "not_found", "No such block type.")
        try:
            ctx = context_for(body.get("project_id"), body.get("system_id"), deps=deps, mode="preview")
            return {name: cls().choices(ctx, name) for name in cls.choice_options}
        except NotInProject:
            return _error(404, "not_found", "No such system version in this project.")
        except PlatformUnavailable:
            ref = new_error_ref()
            logger.error("choices: the platform database is unreachable, ref %s", ref)
            return _error(503, "platform_unavailable", "The platform database is unreachable.", error_ref=ref)

    @app.post("/v1/render")
    async def render_route(request: Request):
        body = await _body_within(request, max_body_bytes)
        if body is None:
            return _error(413, "too_large", f"A snapshot may be at most {max_body_bytes} bytes.")
        try:
            snapshot = json.loads(body)
        except ValueError:
            snapshot = None
        if not isinstance(snapshot, dict):
            return JSONResponse(status_code=422, content={"problems": [
                {"instance_id": None, "code": "invalid_snapshot", "pointer": "",
                 "message": "the body must be a JSON object"}]})
        if not slots.acquire(blocking=False):
            return _error(503, "busy", "Too many reports are being rendered; try again shortly.")
        try:
            return await run_in_threadpool(_render, snapshot)
        finally:
            slots.release()

    def _render(snapshot: dict):
        try:
            return render(snapshot, deps)
        except InvalidSnapshot as exc:
            return JSONResponse(status_code=422, content={"problems": exc.problems})
        except NotFound:
            return _error(404, "not_found", "No such system version in this project.")
        except PlatformUnavailable:
            ref = new_error_ref()
            logger.error("render: the platform database is unreachable, ref %s", ref)
            return _error(503, "platform_unavailable", "The platform database is unreachable.", error_ref=ref)

    return app


_app = None


def __getattr__(name):
    """`report_service.app` for uvicorn, built on first access."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
