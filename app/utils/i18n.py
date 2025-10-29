"""Localization helpers for backend responses."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from app.localization import DEFAULT_LANGUAGE, ENABLED_LANGUAGE_CODES, get_translation


def resolve_locale(
    request: Request,
    user_preferred_language: str | None = None,
) -> str:
    """Resolve the best locale for the current request."""

    if user_preferred_language in ENABLED_LANGUAGE_CODES:
        return user_preferred_language  # type: ignore[return-value]

    header = request.headers.get("Accept-Language", "")
    if header:
        for raw in header.split(","):
            code = raw.split(";")[0].strip().lower()
            if not code:
                continue
            if code in ENABLED_LANGUAGE_CODES:
                return code
            if "-" in code:
                base = code.split("-")[0]
                if base in ENABLED_LANGUAGE_CODES:
                    return base

    return DEFAULT_LANGUAGE


def translate(
    message_key: str,
    request: Request,
    user_preferred_language: str | None = None,
    default: str | None = None,
    **format_args: Any,
) -> str:
    """Translate a backend message key using request context."""

    locale = resolve_locale(request, user_preferred_language)
    translation = get_translation(f"backend.{message_key}", locale, default=default)

    if translation is None:
        translation = default or message_key

    if format_args:
        try:
            translation = translation.format(**format_args)
        except (KeyError, ValueError):
            pass

    return translation
