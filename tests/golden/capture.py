"""Capture the goldens of tests/golden/.

test_compat_golden.py compares the renderer's output against these files. Running this script
overwrites them, so run it only to re-baseline on purpose, from the repository root (AISC_INSTALL_DIR
overrides where the superproject is, as for the suite):

    .venv/bin/python tests/golden/capture.py [output folder]

It builds the throwaway bed the suite uses (conftest.build_bed, removed afterwards), renders the cases
of `golden_cases.CASES` with the suite's dependencies in mode=preview (HTML) and mode=pdf (the PDF's
text per page), each twice to prove the output is deterministic, and writes them next to this file or
into the given folder. MANIFEST.json names the commit the renderer was at.
"""
from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))   # the repository root: report_renderer
sys.path.insert(0, str(HERE.parent))       # tests/: conftest finds the superproject's report bed
sys.path.insert(0, str(HERE))

from conftest import FIXED_NOW, bed_sources, build_bed  # noqa: E402
from golden_cases import CASES, snapshot_for  # noqa: E402


def pdf_pages(pdf_b64: str) -> list[str]:
    from pypdf import PdfReader

    return [p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(pdf_b64))).pages]


def main(out_dir: Path = HERE) -> None:
    from report_renderer.context import Deps
    from report_renderer.document import render
    from report_renderer.registry import build_registry
    from report_renderer.superset import NoImageProvider

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bed = build_bed("golden")
    try:
        deps = Deps(registry=build_registry(), sources=bed_sources(bed), images=NoImageProvider(),
                    clock=lambda: FIXED_NOW, chart_data=None)
        manifest = {}
        for name, case in CASES.items():
            html1 = render(snapshot_for(case, "preview"), deps)
            html2 = render(snapshot_for(case, "preview"), deps)
            assert html1 == html2, f"{name}: preview output is not deterministic"
            (out_dir / f"{name}.html").write_text(html1["html"], encoding="utf-8")
            (out_dir / f"{name}.statuses.json").write_text(json.dumps(html1["block_statuses"], indent=1),
                                                          encoding="utf-8")
            entry = {"html": f"{name}.html"}
            if case.get("pdf"):
                p1 = pdf_pages(render(snapshot_for(case, "pdf"), deps)["pdf_base64"])
                p2 = pdf_pages(render(snapshot_for(case, "pdf"), deps)["pdf_base64"])
                assert p1 == p2, f"{name}: pdf text is not deterministic"
                (out_dir / f"{name}.pdf.json").write_text(json.dumps(p1, indent=1, ensure_ascii=False),
                                                         encoding="utf-8")
                entry["pdf_text"] = f"{name}.pdf.json"
            manifest[name] = entry
            print("captured", name)
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, capture_output=True,
                              text=True).stdout.strip()
        (out_dir / "MANIFEST.json").write_text(json.dumps({"renderer_commit": head, "cases": manifest}, indent=1)
                                               + "\n")
    finally:
        bed.stop()


if __name__ == "__main__":
    main(*sys.argv[1:2])
