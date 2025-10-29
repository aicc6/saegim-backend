"""Supported language metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    native_name: str

    SUPPORTED_CODES: ClassVar[set[str]] = {"ko", "en", "ja"}

    @classmethod
    def validate(cls, code: str) -> str:
        if code not in cls.SUPPORTED_CODES:
            raise ValueError(f"Unsupported language code: {code}")
        return code


ENABLED_LANGUAGES: tuple[Language, ...] = (
    Language(code="ko", name="Korean", native_name="한국어"),
    Language(code="en", name="English", native_name="English"),
    Language(code="ja", name="Japanese", native_name="日本語"),
)

DEFAULT_LANGUAGE = ENABLED_LANGUAGES[0].code
ENABLED_LANGUAGE_CODES = {lang.code for lang in ENABLED_LANGUAGES}
