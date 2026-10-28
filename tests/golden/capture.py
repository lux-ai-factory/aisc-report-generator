"""Capture the compatibility goldens of tests/golden/.

The goldens are the renderer's output at commit df14131 (MANIFEST.json names it), the baseline that
test_compat_golden.py compares against. Running this script again overwrites them, so run it only to
re-baseline on purpose, from the repository root, with AISC_INSTALL_DIR at the aisc superproject:

    uv run --extra dev python tests/golden/capture.py

It builds a throwaway report bed (aisc-t-golden-*, removed afterwards), renders the cases of
`golden_cases.CASES` in mode=preview (HTML) and mode=pdf (the PDF's text per page), each twice to
prove the output is deterministic, and writes them next to this file.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
AISC_INSTALL = Path(os.environ.get("AISC_INSTALL_DIR", HERE.parents[2] / "aisc-install"))
sys.path.insert(0, str(AISC_INSTALL / "scripts/lib"))

import report_bed  # noqa: E402
from golden_cases import CASES, FIXED_NOW, snapshot_for  # noqa: E402


def pdf_pages(pdf_b64: str) -> list[str]:
    from pypdf import PdfReader

    return [p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(pdf_b64))).pages]


def main() -> None:
    from report_renderer.context import Deps
    from report_renderer.data import Sources
    from report_renderer.document import render
    from report_renderer.registry import build_registry
    from report_renderer.superset import NoImageProvider

    report_bed.check_dsn_env()
    bed = report_bed.build("golden")
    try:
        env = bed.env()
        sources = Sources(platform_dsn=env["REPORT_PLATFORM_DATABASE_URL"],
                          superset_dsn=env["REPORT_SUPERSET_DATABASE_URL"],
                          project_db_template=env["REPORT_PROJECT_DB_URL"],
                          airo_vocab_path=env["REPORT_AIRO_VOCAB_PATH"],
                          objectives_csv_path=env["REPORT_OBJECTIVES_CSV_PATH"],
                          superset_url="http://superset.invalid:8188")
        deps = Deps(registry=build_registry(), sources=sources, images=NoImageProvider(),
                    clock=lambda: FIXED_NOW, chart_data=None)
        manifest = {}
        for name, case in CASES.items():
            html1 = render(snapshot_for(case, "preview"), deps)
            html2 = render(snapshot_for(case, "preview"), deps)
            assert html1 == html2, f"{name}: preview output is not deterministic"
            (HERE / f"{name}.html").write_text(html1["html"], encoding="utf-8")
            (HERE / f"{name}.statuses.json").write_text(json.dumps(html1["block_statuses"], indent=1), encoding="utf-8")
            entry = {"html": f"{name}.html"}
            if case.get("pdf"):
                p1 = pdf_pages(render(snapshot_for(case, "pdf"), deps)["pdf_base64"])
                p2 = pdf_pages(render(snapshot_for(case, "pdf"), deps)["pdf_base64"])
                assert p1 == p2, f"{name}: pdf text is not deterministic"
                (HERE / f"{name}.pdf.json").write_text(json.dumps(p1, indent=1, ensure_ascii=False), encoding="utf-8")
                entry["pdf_text"] = f"{name}.pdf.json"
            manifest[name] = entry
            print("captured", name)
        import subprocess

        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, capture_output=True, text=True).stdout.strip()
        (HERE / "MANIFEST.json").write_text(json.dumps({"renderer_commit": head, "cases": manifest}, indent=1))
    finally:
        bed.stop()


if __name__ == "__main__":
    main()
