"""The report's language file (English only).

Reports are English only. The one language file is the built-in `report_renderer/i18n/en.json`; no other
folder is read, so no language can be added by dropping a file. Message ids are the English texts, and
`en.json` may hold only singular forms (`"<msgid>|one"`). The file is read per call, never at import. If it
cannot be read, English without singular forms is used and a warning is logged.
"""
from __future__ import annotations

import logging
from pathlib import Path

from aisc_report_plugin_interface.i18n import LanguageFile, read_language_file, translator as make_translator

logger = logging.getLogger("report_renderer.languages")
BUILTIN_DIR = Path(__file__).resolve().parent / "i18n"
ENGLISH = LanguageFile(code="en", name="English", messages={})


def language_files() -> dict[str, LanguageFile]:
    """{"en": the built-in English file}."""
    try:
        return {"en": read_language_file(BUILTIN_DIR / "en.json")}
    except (OSError, ValueError) as exc:
        logger.warning("cannot read en.json, using English without singular forms: %s", exc)
        return {"en": ENGLISH}


def languages() -> list[dict]:
    """The offered languages: English only."""
    return [{"code": "en", "name": "English"}]


def language_file() -> LanguageFile:
    """The English file."""
    return language_files()["en"]


def translator():
    """(t, language file) for English."""
    lf = language_file()
    return make_translator(lf), lf
