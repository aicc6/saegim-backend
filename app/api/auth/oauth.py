"""
OAuth 소셜 로그인 API 라우터
Google OAuth 로그인 처리
"""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.deps import AuthServiceDep
from app.utils.cookie import CookieUtils

router = APIRouter(prefix="/google", tags=["Oauth"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.get("/login")
async def google_login():
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
    auth_service: AuthServiceDep,
    code: str,
):
    """구글 OAuth 콜백 처리"""
    url, access_token, refresh_token = await auth_service.google_callback(code)

    response = RedirectResponse(
        url=url,
    )

    if access_token and refresh_token:
        CookieUtils.set_oauth_cookies(response, access_token, refresh_token)

    return response
