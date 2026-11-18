"""The report's look, sanitised from the snapshot's `style`.

This is a trust boundary: the snapshot comes from the network, so only valid
values reach the document. Colours must be #rrggbb, the font and marking must
be known choices, text is clipped, and the logo is validated into a data URI.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from markupsafe import Markup

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# the fonts the report image ships, and the mark levels
FONT_STACKS = {
    "inter": '"Inter", "Liberation Sans", Arial, sans-serif',
    "liberation-sans": '"Liberation Sans", Arial, sans-serif',
    "liberation-serif": '"Liberation Serif", "Times New Roman", serif',
    "roboto": '"Roboto", "Liberation Sans", Arial, sans-serif',
    "dejavu-sans": '"DejaVu Sans", Verdana, sans-serif',
    "dejavu-serif": '"DejaVu Serif", Georgia, serif',
}
MARKING_LABELS = {
    "public": "Public",
    "internal": "Internal",
    "confidential": "Confidential",
    "strictly_confidential": "Strictly confidential",
}
LOGO_MIMES = {"image/png", "image/jpeg", "image/svg+xml"}
LOGO_MAX_BASE64 = 1_400_000

DEFAULT_PRIMARY = "#000fdf"   # LAIF blue
DEFAULT_ACCENT = "#ff007e"    # LAIF pink
DEFAULT_FONT = "inter"
DEFAULT_FONT_SIZE = 11


def css_text(value: str) -> Markup:
    """Quote a string for a CSS `content` value, escaping quotes and slashes."""
    return Markup('"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"')


def _logo_data_uri(value) -> str:
    if not isinstance(value, dict):
        return ""
    mime = value.get("mime")
    data = value.get("data_base64")
    if mime not in LOGO_MIMES or not isinstance(data, str) or not data:
        return ""
    return f"data:{mime};base64,{data[:LOGO_MAX_BASE64]}"


def _clamp_size(value, default: float) -> int | float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = default
    rounded = round(min(16, max(8, value)), 1)
    return rounded if rounded != int(rounded) else int(rounded)


@dataclass(frozen=True)
class ReportStyle:
    """The validated look of the document (every value is reportable)."""

    report_version: int
    report_title: str
    subtitle: str
    primary_color: str
    accent_color: str
    font: str
    font_stack: str
    font_size_pt: int | float
    header_text: str
    footer_text: str
    marking: str
    marking_label: str
    show_document_id: bool
    document_id: str
    fingerprint: str
    logo: str  # a data URI, or ""

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> ReportStyle:
        style = snapshot.get("style") if isinstance(snapshot.get("style"), dict) else {}

        def text(key: str, limit: int) -> str:
            value = style.get(key)
            return value.strip()[:limit] if isinstance(value, str) else ""

        def colour(key: str, default: str) -> str:
            value = style.get(key)
            return value.lower() if isinstance(value, str) and _HEX.match(value) else default

        try:
            report_version = max(1, int(style.get("report_version") or 1))
        except (TypeError, ValueError):
            report_version = 1

        font = style.get("font") if isinstance(style.get("font"), str) else DEFAULT_FONT
        marking = style.get("marking") if isinstance(style.get("marking"), str) else "none"
        return cls(
            report_version=report_version,
            report_title=text("report_title", 200),
            subtitle=text("subtitle", 300),
            primary_color=colour("primary_color", DEFAULT_PRIMARY),
            accent_color=colour("accent_color", DEFAULT_ACCENT),
            font=font if font in FONT_STACKS else DEFAULT_FONT,
            font_stack=FONT_STACKS.get(font, FONT_STACKS[DEFAULT_FONT]),
            font_size_pt=_clamp_size(style.get("font_size_pt"), DEFAULT_FONT_SIZE),
            header_text=text("header_text", 120),
            footer_text=text("footer_text", 120),
            marking=marking if marking in MARKING_LABELS else "none",
            marking_label=MARKING_LABELS.get(marking, ""),
            show_document_id=bool(style.get("show_document_id", False)),
            document_id=text("document_id", 64),
            fingerprint=text("fingerprint", 64),
            logo=_logo_data_uri(style.get("logo")),
        )
