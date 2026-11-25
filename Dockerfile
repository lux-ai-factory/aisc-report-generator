# syntax=docker/dockerfile:1.19
# The report renderer. Build contexts: this repo, plus `interface`, the report plugin interface
# (docker compose additional_contexts, or docker build --build-context; in aisc: apps/report-generator
# and shared/report-plugin-interface). The tool renderers in plugins/ are built in; a tool without
# one gets the generic results table.
# Stand-ins for the `vocab` and `objectives_data` build contexts. The baked stack (docker-compose.baked.yml) passes
# aisc's vocabulary and control objectives data folders under those names and the files go into the image; the
# development stack passes none and mounts the files at /data over the stand-ins, so this build works for both. Each
# stand-in says which file to build with, so a renderer that reads one fails loudly instead of reading nothing.
FROM python:3.12.15-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS vocab
RUN for f in airo_vocab.json vair_vocab.json; do \
      echo "$f is a stand-in: build this image with docker-compose.baked.yml, which passes the vocab build context" > /$f; done
FROM python:3.12.15-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS objectives_data
RUN echo "ai_act_control_objectives.csv is a stand-in: build this image with docker-compose.baked.yml, which passes the objectives_data build context" \
      > /ai_act_control_objectives.csv

FROM python:3.12.15-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
COPY --from=ghcr.io/astral-sh/uv:0.9.9@sha256:f6e3549ed287fee0ddde2460a2a74a2d74366f84b04aaa34c1f19fec40da8652 /uv /uvx /bin/

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

# the vocabularies and the control objectives the report names its objectives and risks from
COPY --chmod=a=rX --from=vocab /airo_vocab.json /vair_vocab.json /data/
COPY --chmod=a=rX --from=objectives_data /ai_act_control_objectives.csv /data/

# not root: the renderer decodes images from templates and needs no privilege
RUN useradd --system --create-home --uid 10001 renderer
USER renderer

EXPOSE 8001
CMD ["uvicorn", "report_service:app", "--host", "0.0.0.0", "--port", "8001"]
