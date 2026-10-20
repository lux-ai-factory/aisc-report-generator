"""Shared pieces of the built-in blocks."""
from __future__ import annotations

from markupsafe import escape
from aisc_report_plugin_interface import BlockResult
from aisc_report_plugin_interface.i18n import fill


def _english(msgid, **params) -> str:
    return fill(msgid, params)


def newer_notice(number, t=None) -> str:
    return (t or _english)("Newer results exist for version {number}.", number=number)


def empty_result(text: str) -> BlockResult:
    """A block with no data for the version says so and is `empty`."""
    return BlockResult(html=f'<p class="placeholder">{escape(text)}</p>', status="empty")


def finish(html, notices, *, newest_newer: int | None, status="ok", t=None) -> BlockResult:
    """A block whose data exists for a newer version is `stale`, with the notice first."""
    notices = list(notices)
    if status == "ok" and newest_newer is not None:
        status = "stale"
        notices.insert(0, newer_notice(newest_newer, t))
    return BlockResult(html=str(html), status=status, notices=notices)


def ymd(value) -> str:
    return value.strftime("%Y-%m-%d") if value is not None else ""
