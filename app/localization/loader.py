"""Translation loader utilities."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.localization.languages import DEFAULT_LANGUAGE, ENABLED_LANGUAGE_CODES

_LOCALES_DIR = Path(__file__).resolve().parent / "locales"


def _locale_path(locale: str) -> Path:
    return _LOCALES_DIR / f"{locale}.json"


@lru_cache(maxsize=None)
def _load_locale(locale: str) -> dict[str, Any]:
    path = _locale_path(locale)
    if not path.exists():
        raise FileNotFoundError(f"Missing locale file for '{locale}': {path}")

    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def get_translations(locale: str) -> dict[str, Any]:
    if locale not in ENABLED_LANGUAGE_CODES:
        locale = DEFAULT_LANGUAGE
    return _load_locale(locale)


def get_translation(key: str, locale: str, *, default: str | None = None) -> str | None:
    translations = get_translations(locale)
    value = translations
    for segment in key.split("."):
        if isinstance(value, dict) and segment in value:
            value = value[segment]
        else:
            value = None
            break

    if isinstance(value, str):
        return value
    return default
