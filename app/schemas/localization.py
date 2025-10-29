"""Schematics for localization endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.schemas.base import BaseResponse


class LanguageOption(BaseModel):
    code: str
    name: str
    native_name: str


class GetLanguagesResponse(BaseResponse[list[LanguageOption]]):
    pass


class TranslationPayload(BaseModel):
    locale: str
    fallback_locale: str
    translations: dict[str, Any]


class GetTranslationsResponse(BaseResponse[TranslationPayload]):
    pass
