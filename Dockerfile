FROM python:3.12-slim

WORKDIR /app

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
    libjpeg62-turbo \
    libopenjp2-7 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libxml2 \
    libxslt1.1 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    jinja2>=3.1.6 \
    pyyaml>=6.0.2 \
    sqlalchemy>=2.0.48 \
    weasyprint>=68.1

COPY . .

RUN mkdir -p /app/reports /app/data

EXPOSE 8001

CMD ["python", "report_service.py"]