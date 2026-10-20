"""Every font a template may choose is installed by the image (report_renderer/style.py FONTS)."""
from pathlib import Path

from conftest import need

PACKAGES = {"inter": "fonts-inter", "liberation-sans": "fonts-liberation", "liberation-serif": "fonts-liberation",
            "roboto": "fonts-roboto-unhinted", "dejavu-sans": "fonts-dejavu-core", "dejavu-serif": "fonts-dejavu-core"}


def test_the_dockerfile_installs_every_offered_font():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    for font in need("report_renderer.style", "FONTS"):
        assert PACKAGES[font["id"]] in dockerfile, font["id"]
