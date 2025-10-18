from fastapi import Response
from fastapi.responses import RedirectResponse

from app.core.config import CookieSameSite, get_settings

settings = get_settings()


class CookieUtils:
    @staticmethod
    def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
        """인증 쿠키 설정"""
        samesite = (
            CookieSameSite.STRICT
            if settings.is_production
            else settings.cookie_samesite
        )

        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=settings.cookie_httponly,
            secure=settings.cookie_secure,
            samesite=samesite.value,
            max_age=settings.jwt_access_token_expire_minutes * 60,
            path="/",
            domain=settings.cookie_domain,
        )

        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=settings.cookie_httponly,
            secure=settings.cookie_secure,
            samesite=samesite.value,
            max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
            path="/",
            domain=settings.cookie_domain,
        )

    @staticmethod
    def clear_auth_cookies(response: Response):
        """인증 쿠키 삭제"""
        for key in ["access_token", "refresh_token", "session"]:
            response.delete_cookie(
                key=key,
                path="/",
                secure=settings.cookie_secure,
                httponly=settings.cookie_httponly,
                samesite=settings.cookie_samesite.value,
                domain=settings.cookie_domain,
            )

    @staticmethod
    def set_oauth_cookies(
        response: RedirectResponse,
        access_token: str,
        refresh_token: str,
    ):
        """OAuth 인증 쿠키 설정"""
        # samesite 값을 명시적으로 계산해서 Literal 타입 보장
        samesite = (
            CookieSameSite.STRICT
            if settings.is_production
            else settings.cookie_samesite
        )

        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=settings.cookie_httponly,
            secure=settings.is_production,
            samesite=samesite.value,
            max_age=settings.jwt_access_token_expire_minutes * 60,
            path="/",
            domain=settings.cookie_domain,
        )

        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=settings.cookie_httponly,
            secure=settings.is_production,
            samesite=samesite.value,
            max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
            path="/",
            domain=settings.cookie_domain,
        )
