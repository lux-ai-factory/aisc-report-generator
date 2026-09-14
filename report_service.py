from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from report_generator import ReportGenerator


def _env_path(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value if value else None


def build_generator(project: str | int | None = None) -> ReportGenerator:
    resolved_project: str | int | None = project if project is not None else os.getenv("PROJECT_NAME")
    if isinstance(resolved_project, str) and resolved_project.isdigit():
        resolved_project = int(resolved_project)

    return ReportGenerator(
        output_path=os.getenv("REPORT_OUTPUT_PATH", "./reports"),
        filename=os.getenv("REPORT_FILENAME", "assessment_report"),
        plugin_path=_env_path("REPORT_PLUGIN_PATH", "./plugins"),
        logo_path=os.getenv("REPORT_LOGO_PATH", "resources/LAIF_RGB.svg"),
        system_info_path=_env_path("REPORT_SYSTEM_INFO"),
        custom_report_style=_env_path("REPORT_STYLE_PATH"),
        db_url=os.getenv("DB_URL"),
        project=resolved_project,
        tool_plots_path=_env_path("REPORT_TOOL_PLOTS_PATH") or _env_path("TMP_PLOTS_PATH"),
    )


class ReportRequestHandler(BaseHTTPRequestHandler):
    server_version = "vera-report-generator/1.0"

    @property
    def output_root(self) -> Path:
        return Path(os.getenv("REPORT_OUTPUT_PATH", "./reports")).resolve()

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_pdf(self, pdf_path: Path) -> None:
        pdf_path = pdf_path.resolve()
        if not pdf_path.exists() or not pdf_path.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "PDF not found"})
            return

        if self.output_root not in pdf_path.parents and pdf_path != self.output_root:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Invalid report path"})
            return

        data = pdf_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'inline; filename="{pdf_path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler signature
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler signature
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path in {"/", "/health"}:
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "vera-report-generator",
                },
            )
            return

        if parsed.path == "/generate":
            project_param = params.get("project_id", params.get("project", []))
            project_value: str | int | None = None
            if project_param:
                raw_project = unquote(project_param[0])
                project_value = int(raw_project) if raw_project.isdigit() else raw_project

            generator = build_generator(project_value)
            pdf_path = generator.run()
            redirect_target = f"/reports/{quote(pdf_path.name)}"

            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", redirect_target)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        if parsed.path.startswith("/reports/"):
            requested_name = Path(unquote(parsed.path.removeprefix("/reports/")))
            if requested_name.name != requested_name.as_posix():
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid report name"})
                return

            self._send_pdf(self.output_root / requested_name.name)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})


def main() -> None:
    host = os.getenv("REPORT_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("REPORT_SERVICE_PORT", "8001"))
    server = ThreadingHTTPServer((host, port), ReportRequestHandler)
    print(f"[report-service] listening on {host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()