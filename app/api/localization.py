"""Localization related public endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Request, status

from app.localization import (
    DEFAULT_LANGUAGE,
    ENABLED_LANGUAGES,
    ENABLED_LANGUAGE_CODES,
    get_translations as load_translations,
)
from app.schemas.localization import (
    GetLanguagesResponse,
    GetTranslationsResponse,
    LanguageOption,
    TranslationPayload,
    LanguageCode,
)
from app.utils.i18n import translate

router = APIRouter(tags=["Localization"])


@router.get("/languages", response_model=GetLanguagesResponse)
def list_languages(http_request: Request) -> GetLanguagesResponse:
    """Return the list of languages supported by the application."""

    data = [
        LanguageOption(
            code=LanguageCode(lang.code), name=lang.name, native_name=lang.native_name
        )
        for lang in ENABLED_LANGUAGES
    ]

    return GetLanguagesResponse(
        data=data,
        message=translate(
            "localization.languages_loaded",
            http_request,
            default="지원 언어 목록을 불러왔습니다.",
        ),
    )


@router.get(
    "/translations/{locale}",
    response_model=GetTranslationsResponse,
)
def get_translations(
    http_request: Request,  # 기본값 없는 인자를 먼저
    locale: str = Path(..., description="요청할 언어 코드 (ko, en, ja)"),
) -> GetTranslationsResponse:
    """Return translation payload for the requested locale.

    Falls back to the default language when the locale is not supported.
    """

    fallback_locale = LanguageCode(DEFAULT_LANGUAGE)
    resolved_locale = (
        LanguageCode(locale)
        if locale in ENABLED_LANGUAGE_CODES
        else fallback_locale
    )
    
    try:
        translations = load_translations(resolved_locale.value)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    payload = TranslationPayload(
        fallback_locale=fallback_locale,
        translations=translations,
        locale=resolved_locale,
    )

    return GetTranslationsResponse(
        data=payload,
        message=translate(
            "localization.translations_loaded",
            http_request,
            user_preferred_language=resolved_locale.value,
            default="번역 데이터를 불러왔습니다.",
        ),
    )
