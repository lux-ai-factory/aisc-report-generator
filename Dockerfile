# The report image: ONE lean FastAPI server (src/app.py). The backend (Django) owns all data and
# hands it over as a JSON snapshot; this service only draws the document (HTML preview or PDF via
# weasyprint) from that snapshot and reads no database. Base image and build pattern match
# apps/backend and apps/qualification (the repo's uv image, src-layout, venv).
FROM ghcr.io/astral-sh/uv:python3.12-alpine AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# weasyprint system libraries and a font: the report is drawn with them
RUN apk add --no-cache \
    pango cairo gdk-pixbuf fontconfig freetype libffi \
    libjpeg-turbo openjpeg lcms2 shared-mime-info \
    ttf-dejavu

# ---- Builder: install the locked deps ----
FROM base AS builder

WORKDIR /aisc/apps/report
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ---- Final runtime image ----
FROM base AS runtime

ENV UV_NO_SYNC=1
COPY --from=builder /app/.venv /app/.venv

# src/ lands at /app so `uvicorn app:app` picks the report service up
WORKDIR /app
COPY src/ ./

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
