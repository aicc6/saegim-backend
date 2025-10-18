"""
OAuth 인증 서비스
"""

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import AccountType, OAuthProvider
from app.core.config import get_settings
from app.core.errors import OAuthErrors
from app.core.http_client import http_client
from app.exceptions.auth import DeletedAccountException
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.schemas.auth import GoogleLoginRequest
from app.schemas.oauth import GoogleOAuthResponse, OAuthUserInfo
from app.services.base import BaseService

# 로거 설정
logger = logging.getLogger(__name__)

settings = get_settings()


class GoogleOAuthService(BaseService):
    """구글 OAuth 서비스"""

    TOKEN_INFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"

    def __init__(self, db: Session):
        """초기화"""
        super().__init__(db)
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.redirect_uri = settings.google_redirect_uri
        self.token_url = settings.google_token_uri
        self.userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        self.settings = get_settings()

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
            raise OAuthErrors.token_request_failed(str(e.detail)) from e

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

            assert user_id is not None, "구글 사용자 정보에 ID가 포함되어 있지 않음"

            return OAuthUserInfo(
                id=user_id,  # 구글 사용자 ID (sub, id, 또는 email 폴백)
                email=user_data["email"],
                name=user_data.get("name", ""),
                picture=user_data.get("picture"),
            )
        except HTTPException as e:
            logger.error("Failed to get user info from Google API")
            raise OAuthErrors.userinfo_request_failed() from e

    async def process_oauth_callback(self, code: str, tx: Session):
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
        result = tx.execute(stmt)
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

            raise DeletedAccountException(
                email=user.email,
                days_remaining=(
                    30 - (current_time_naive - deleted_time).days
                    if deleted_time >= current_time_naive - timedelta(days=30)
                    else None
                ),
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
            tx.add(user)

        # OAuth 토큰 저장/업데이트
        oauth_token_result = tx.execute(
            select(OAuthToken).where(
                OAuthToken.user_id == user.id,
                OAuthToken.provider == OAuthProvider.GOOGLE.value,
            )
        )
        oauth_token = oauth_token_result.scalar_one_or_none()

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
            tx.add(oauth_token)

        return user, oauth_token

    async def authenticate(self, request: GoogleLoginRequest, tx: Session) -> User:
        token_info = await self._fetch_token_info(request.id_token)
        token_email = token_info.get("email")

        if not token_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="구글 계정 이메일을 확인할 수 없습니다.",
            )

        user = self.__find_user(token_email, request.email, tx)

        if user:
            self.__ensure_not_soft_deleted(user)
            self.__update_existing_user(user, request, token_info)
        else:
            user = self.__create_user(token_email, request, token_info, tx)

        expires_at = self.__extract_expiration(token_info)
        self.__upsert_oauth_token(user, request.id_token, expires_at, tx)

        logger.info("Google ID 토큰 로그인 성공", extra={"user_id": str(user.id)})

        return user

    async def _fetch_token_info(self, id_token: str) -> dict[str, str]:
        url = f"{self.TOKEN_INFO_ENDPOINT}?id_token={quote_plus(id_token)}"

        try:
            token_info: dict[str, str] = await http_client.get_json(url)
        except HTTPException as exc:
            logger.warning(
                "Google ID 토큰 검증 실패",
                extra={"status_code": exc.status_code, "detail": exc.detail},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않은 구글 인증 정보입니다.",
            ) from exc

        self._validate_token_info(token_info)
        return token_info

    def _validate_token_info(self, token_info: dict[str, str]) -> None:
        audience = token_info.get("aud")
        if not audience:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="구글 토큰 정보에 aud 값이 없습니다.",
            )

        if audience not in self.settings.google_allowed_audiences:
            logger.warning(
                "허용되지 않은 Google 클라이언트 ID",
                extra={
                    "aud": audience,
                    "allowed": self.settings.google_allowed_audiences,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="허용되지 않은 구글 클라이언트입니다.",
            )

        issuer = token_info.get("iss")
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="허용되지 않은 구글 토큰 발급처입니다.",
            )

        email_verified = str(token_info.get("email_verified", "")).lower()
        if email_verified not in {"true", "1"}:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="구글 계정 이메일이 인증되지 않았습니다.",
            )

        expires_at = token_info.get("exp")
        if expires_at:
            try:
                if int(expires_at) <= int(datetime.now(UTC).timestamp()):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="만료된 구글 토큰입니다.",
                    )
            except ValueError:
                logger.debug("만료 시각 파싱 실패", extra={"exp": expires_at})

    def __find_user(
        self, token_email: str, requested_email: str, tx: Session
    ) -> User | None:
        stmt = select(User).where(User.email == token_email)
        user = tx.execute(stmt).scalar_one_or_none()

        if user is None and requested_email.lower() != token_email.lower():
            stmt = select(User).where(User.email == requested_email)
            user = tx.execute(stmt).scalar_one_or_none()

        return user

    @staticmethod
    def __ensure_not_soft_deleted(user: User) -> None:
        if user.deleted_at is None:
            return

        now = datetime.now(user.deleted_at.tzinfo or UTC)
        deleted_at = user.deleted_at.astimezone(UTC)

        if deleted_at >= now.astimezone(UTC) - timedelta(days=30):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "ACCOUNT_DELETED",
                    "message": "탈퇴된 계정입니다. 30일 이내에 복구할 수 있습니다.",
                    "deleted_at": user.deleted_at.isoformat(),
                    "restore_available": True,
                },
            )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "ACCOUNT_PERMANENTLY_DELETED",
                "message": "탈퇴 후 30일이 경과되어 복구할 수 없습니다.",
                "deleted_at": user.deleted_at.isoformat(),
                "restore_available": False,
            },
        )

    def __update_existing_user(
        self, user: User, request: GoogleLoginRequest, token_info: dict[str, str]
    ) -> None:
        if user.account_type == AccountType.EMAIL.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이메일 회원가입 계정이 이미 존재합니다. 이메일 로그인을 이용해주세요.",
            )

        user.account_type = AccountType.SOCIAL.value
        user.provider = OAuthProvider.GOOGLE.value

        provider_id = token_info.get("sub")
        if provider_id:
            user.provider_id = provider_id

        if request.display_name and not user.nickname:
            user.nickname = request.display_name

        if request.photo_url:
            user.profile_image_url = request.photo_url

        user.is_active = True

    def __create_user(
        self,
        token_email: str,
        request: GoogleLoginRequest,
        token_info: dict[str, str],
        tx: Session,
    ) -> User:
        nickname = request.display_name or token_email.split("@")[0]
        provider_id = token_info.get("sub")

        user = User(
            email=token_email,
            nickname=nickname,
            profile_image_url=request.photo_url,
            account_type=AccountType.SOCIAL.value,
            provider=OAuthProvider.GOOGLE.value,
            provider_id=provider_id,
            is_active=True,
        )
        tx.add(user)
        tx.flush()

        return user

    def __upsert_oauth_token(
        self, user: User, id_token: str, expires_at: datetime | None, tx: Session
    ) -> None:
        stmt = select(OAuthToken).where(
            OAuthToken.user_id == user.id,
            OAuthToken.provider == OAuthProvider.GOOGLE.value,
        )
        oauth_token = tx.execute(stmt).scalar_one_or_none()

        if oauth_token:
            oauth_token.access_token = id_token
            oauth_token.refresh_token = None
            oauth_token.expires_at = expires_at
        else:
            oauth_token = OAuthToken(
                user_id=user.id,
                provider=OAuthProvider.GOOGLE.value,
                access_token=id_token,
                refresh_token=None,
                expires_at=expires_at,
            )
            tx.add(oauth_token)

    @staticmethod
    def __extract_expiration(token_info: dict[str, str]) -> datetime | None:
        exp_value = token_info.get("exp")

        if not exp_value:
            return None

        try:
            return datetime.fromtimestamp(int(exp_value), tz=UTC)
        except (TypeError, ValueError):
            logger.debug(
                "Google 토큰 exp 값을 파싱하지 못했습니다.", extra={"exp": exp_value}
            )
            return None
