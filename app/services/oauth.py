"""
OAuth 인증 서비스
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import AccountType, OAuthProvider
from app.core.config import get_settings
from app.core.errors import OAuthErrors
from app.core.http_client import http_client
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.schemas.oauth import GoogleOAuthResponse, OAuthUserInfo
from app.services.base import BaseService

# 로거 설정
logger = logging.getLogger(__name__)

settings = get_settings()


class GoogleOAuthService(BaseService):
    """구글 OAuth 서비스"""

    def __init__(self, db: Session):
        """초기화"""
        super().__init__(db)
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.redirect_uri = settings.google_redirect_uri
        self.token_url = settings.google_token_uri
        self.userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"

    async def get_access_token(self, code: str) -> GoogleOAuthResponse:
        """인증 코드로 액세스 토큰 요청

        Args:
            code: 인증 코드

        Returns:
            GoogleOAuthResponse: 토큰 응답

        Raises:
            HTTPException: 토큰 요청 실패 시
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }

        logger.info(f"Requesting token with redirect_uri: {self.redirect_uri}")
        logger.info(f"Client ID configured: {self.client_id[:8]}...")
        logger.info(f"Token URL: {self.token_url}")

        try:
            response_data = await http_client.post_json(self.token_url, data)
            return GoogleOAuthResponse(**response_data)
        except HTTPException as e:
            logger.error(f"Failed to get access token: {e.detail}")
            raise OAuthErrors.token_request_failed(str(e.detail))

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """액세스 토큰으로 사용자 정보 요청

        Args:
            access_token: 액세스 토큰

        Returns:
            OAuthUserInfo: 사용자 정보

        Raises:
            HTTPException: 사용자 정보 요청 실패 시
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            user_data = await http_client.get_json(self.userinfo_url, headers=headers)

            # user_data is already parsed from http_client.get_json()
            # 디버깅: 구글 API 응답 확인
            print(f"Google API Response: {user_data}")

            # 구글 userinfo API 응답 구조 확인 및 안전한 ID 추출
            user_id = (
                user_data.get("sub") or user_data.get("id") or user_data.get("email")
            )

            return OAuthUserInfo(
                id=user_id,  # 구글 사용자 ID (sub, id, 또는 email 폴백)
                email=user_data["email"],
                name=user_data.get("name", ""),
                picture=user_data.get("picture"),
            )
        except HTTPException:
            logger.error("Failed to get user info from Google API")
            raise OAuthErrors.userinfo_request_failed()

    async def process_oauth_callback(
        self,
        code: str,
    ) -> tuple[User, OAuthToken]:
        """OAuth 콜백 처리

        Args:
            code: 인증 코드
            db: 데이터베이스 세션

        Returns:
            Tuple[User, OAuthToken]: (사용자, OAuth 토큰)
        """
        # 액세스 토큰 요청
        token_response = await self.get_access_token(code)

        # 사용자 정보 요청
        user_info = await self.get_user_info(token_response.access_token)

        # 기존 사용자 확인 또는 새로 생성
        stmt = select(User).where(User.email == user_info.email)
        result = self._db.execute(stmt)
        user = result.scalar_one_or_none()

        if user and user.deleted_at is not None:
            # timezone을 일치시켜서 비교
            current_time = (
                datetime.now(user.deleted_at.tzinfo)
                if user.deleted_at.tzinfo
                else datetime.now()
            )
            deleted_time = (
                user.deleted_at.replace(tzinfo=None)
                if user.deleted_at.tzinfo
                else user.deleted_at
            )
            current_time_naive = (
                current_time.replace(tzinfo=None)
                if current_time.tzinfo
                else current_time
            )

            # 30일 이내인지 확인
            if deleted_time >= current_time_naive - timedelta(days=30):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "ACCOUNT_DELETED",
                        "message": "탈퇴된 계정입니다. 30일 이내에 복구할 수 있습니다.",
                        "deleted_at": user.deleted_at.isoformat(),
                        "restore_available": True,
                        "days_remaining": 30 - (current_time_naive - deleted_time).days,
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "ACCOUNT_PERMANENTLY_DELETED",
                        "message": "탈퇴 후 30일이 경과되어 복구할 수 없습니다.",
                        "deleted_at": user.deleted_at.isoformat(),
                        "restore_available": False,
                    },
                )

        if not user:
            user = User(
                email=user_info.email,
                nickname=user_info.name,
                profile_image_url=user_info.picture,
                account_type=AccountType.SOCIAL.value,
                provider=OAuthProvider.GOOGLE.value,
                provider_id=user_info.id,  # 구글 사용자 ID 설정
                is_active=True,
            )
            self._db.add(user)
            self._db.commit()
            self._db.refresh(user)

        # OAuth 토큰 저장/업데이트
        stmt = select(OAuthToken).where(
            OAuthToken.user_id == user.id,
            OAuthToken.provider == OAuthProvider.GOOGLE.value,
        )
        result = self._db.execute(stmt)
        oauth_token = result.scalar_one_or_none()

        if oauth_token:
            oauth_token.access_token = token_response.access_token
            oauth_token.refresh_token = token_response.refresh_token
            if token_response.expires_in:
                oauth_token.expires_at = datetime.now(UTC).replace(
                    microsecond=0
                ) + timedelta(seconds=token_response.expires_in)
        else:
            oauth_token = OAuthToken(
                user_id=user.id,
                provider=OAuthProvider.GOOGLE.value,
                access_token=token_response.access_token,
                refresh_token=token_response.refresh_token,
                expires_at=(
                    datetime.now(UTC).replace(microsecond=0)
                    + timedelta(seconds=token_response.expires_in)
                    if token_response.expires_in
                    else None
                ),
            )
            self._db.add(oauth_token)

        self._db.commit()
        self._db.refresh(oauth_token)

        return user, oauth_token
