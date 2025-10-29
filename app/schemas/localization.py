"""Schematics for localization endpoints and shared enums."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.schemas.base import BaseResponse


class LanguageCode(str, Enum):
    KO = "ko"
    EN = "en"
    JA = "ja"


class LanguageOption(BaseModel):
    code: LanguageCode
    name: str
    native_name: str


class GetLanguagesResponse(BaseResponse[list[LanguageOption]]):
    pass


class TranslationPayload(BaseModel):
    locale: LanguageCode
    fallback_locale: LanguageCode
    translations: dict[str, Any]


class GetTranslationsResponse(BaseResponse[TranslationPayload]):
    pass
