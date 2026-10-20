# The report renderer. Build contexts: this repo, plus `interface`, the report plugin interface
# (docker compose additional_contexts, or docker build --build-context; in aisc: apps/report-generator
# and shared/report-plugin-interface). The tool renderers in plugins/ are built in; a tool without
# one gets the generic results table.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libfontconfig1 \
    libfreetype6 \
    libffi8 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libharfbuzz0b \
    libharfbuzz-subset0 \
    libjpeg62-turbo \
    libopenjp2-7 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libxml2 \
    libxslt1.1 \
    shared-mime-info \
    # the fonts a template may choose (report_renderer/style.py FONTS)
    fonts-dejavu-core \
    fonts-inter \
    fonts-liberation \
    fonts-roboto-unhinted \
    && rm -rf /var/lib/apt/lists/*

# the image mirrors aisc's layout, so the path source ../../shared/report-plugin-interface of
# pyproject.toml resolves from the WORKDIR below to this folder
COPY --from=interface . /aisc/shared/report-plugin-interface

WORKDIR /aisc/apps/report-generator
COPY pyproject.toml uv.lock ./
# the bundled tool renderers, installed from the lock like every other package
COPY plugins ./plugins
RUN uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/req.txt \
 && uv pip install --system --no-cache -r /tmp/req.txt && rm /tmp/req.txt
COPY report_service.py ./
COPY report_renderer ./report_renderer

# not root: the renderer decodes images from templates and needs no privilege
RUN useradd --system --create-home --uid 10001 renderer
USER renderer

EXPOSE 8001
CMD ["uvicorn", "report_service:app", "--host", "0.0.0.0", "--port", "8001"]
