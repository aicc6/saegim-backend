"""
OAuth 소셜 로그인 API 라우터
Google OAuth 로그인 처리
"""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token
from app.db.database import get_session
from app.services.oauth import GoogleOAuthService

from app.utils.error_handlers import StandardHTTPException, unauthorized_exception

router = APIRouter(prefix="/google", tags=["Oauth"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.get("/login")
async def google_login() -> RedirectResponse:
    """구글 로그인 페이지로 리다이렉트"""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
    }

    query_string = urlencode(params)
    return RedirectResponse(f"{settings.google_auth_uri}?{query_string}")


@router.get("/callback")
async def google_callback(
    code: str,
    db: Session = Depends(get_session),
) -> RedirectResponse:
    """구글 OAuth 콜백 처리"""
    # 디버깅 로그
    if settings.is_development:
        logger.debug(f"Frontend callback URL: {settings.frontend_callback_url}")
        logger.debug(f"Google client ID: {settings.google_client_id[:8]}...")
    else:
        logger.info("Google OAuth callback initiated")

    try:
        oauth_service = GoogleOAuthService(db)
        user, _ = await oauth_service.process_oauth_callback(code)

        # JWT 토큰 생성
        access_token = create_access_token({"sub": str(user.id)})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        # 프론트엔드로 리다이렉트 (쿠키에 토큰 설정)
        response = RedirectResponse(
            url=f"{settings.frontend_callback_url}?success=true"
        )

        # 쿠키에 토큰 설정 (환경별 보안 강화)
        _set_oauth_cookies(response, access_token, refresh_token)

        # 로그인 성공 로깅
        if settings.is_development:
            logger.debug(f"User logged in: {user.email}")
            logger.debug(
                f"Redirecting to: {settings.frontend_callback_url}?success=true"
            )
        else:
            logger.info(f"User authentication successful: user_id={user.id}")

        return response

    except HTTPException as http_ex:
        # HTTPException 처리 (탈퇴된 계정 등)
        error_detail = http_ex.detail
        if isinstance(error_detail, dict):
            if error_detail.get("error") == "ACCOUNT_DELETED":
                error_url = f"{settings.frontend_callback_url}?error=account_deleted&message={error_detail.get('message', '탈퇴된 계정입니다.')}&restore_available=true&days_remaining={error_detail.get('days_remaining', 0)}"
            elif error_detail.get("error") == "ACCOUNT_PERMANENTLY_DELETED":
                error_url = f"{settings.frontend_callback_url}?error=account_permanently_deleted&message={error_detail.get('message', '탈퇴 후 30일이 경과되어 복구할 수 없습니다.')}&restore_available=false"
            else:
                error_url = f"{settings.frontend_callback_url}?error=login_failed&message={error_detail.get('message', str(http_ex))}"
        else:
            error_url = f"{settings.frontend_callback_url}?error=login_failed&message={str(error_detail)}"

        if settings.is_development:
            logger.debug(f"HTTPException - Error URL: {error_url}")
        else:
            logger.warning(
                f"Authentication error occurred: status={http_ex.status_code}"
            )

        return RedirectResponse(url=error_url)

    except Exception as e:
        error_url = (
            f"{settings.frontend_callback_url}?error=login_failed&message={str(e)}"
        )

        if settings.is_development:
            logger.debug(f"Error URL: {error_url}")
            logger.error(f"OAuth Error: {e}")
        else:
            logger.error(f"OAuth authentication failed: {type(e).__name__}")

        return RedirectResponse(url=error_url)


def _set_oauth_cookies(
    response: RedirectResponse, access_token: str, refresh_token: str
):
    """OAuth 인증 쿠키 설정"""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=settings.cookie_httponly,
        secure=settings.is_production,
        samesite="strict" if settings.is_production else settings.cookie_samesite,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
        domain=settings.cookie_domain,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=settings.cookie_httponly,
        secure=settings.is_production,
        samesite="strict" if settings.is_production else settings.cookie_samesite,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        path="/",
        domain=settings.cookie_domain,
    )
