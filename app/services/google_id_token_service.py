"""Google ID 토큰 기반 로그인 서비스"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import AccountType, OAuthProvider
from app.core.config import get_settings
from app.core.http_client import http_client
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.services.base import BaseService

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from app.api.auth.authentication import GoogleLoginRequest


class GoogleIdTokenService(BaseService):
    """모바일(Android)에서 전달된 Google ID 토큰을 검증하고 로그인 처리"""

    TOKEN_INFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"

    def __init__(self, db: Session):
        super().__init__(db)
        self.settings = get_settings()

    async def authenticate(self, request: GoogleLoginRequest) -> User:
        token_info = await self._fetch_token_info(request.id_token)
        token_email = token_info.get("email")

        if not token_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="구글 계정 이메일을 확인할 수 없습니다.",
            )

        user = self._find_user(token_email, request.email)

        if user:
            self._ensure_not_soft_deleted(user)
            self._update_existing_user(user, request, token_info)
        else:
            user = self._create_user(token_email, request, token_info)

        expires_at = self._extract_expiration(token_info)
        self._upsert_oauth_token(user, request.id_token, expires_at)

        self.db.commit()
        self.db.refresh(user)

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

    def _find_user(self, token_email: str, requested_email: str) -> User | None:
        stmt = select(User).where(User.email == token_email)
        user = self.db.execute(stmt).scalar_one_or_none()

        if user is None and requested_email.lower() != token_email.lower():
            stmt = select(User).where(User.email == requested_email)
            user = self.db.execute(stmt).scalar_one_or_none()

        return user

    @staticmethod
    def _ensure_not_soft_deleted(user: User) -> None:
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

    def _update_existing_user(
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

    def _create_user(
        self,
        token_email: str,
        request: GoogleLoginRequest,
        token_info: dict[str, str],
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
        self.db.add(user)
        self.db.flush()
        return user

    def _upsert_oauth_token(
        self,
        user: User,
        id_token: str,
        expires_at: datetime | None,
    ) -> None:
        stmt = select(OAuthToken).where(
            OAuthToken.user_id == user.id,
            OAuthToken.provider == OAuthProvider.GOOGLE.value,
        )
        oauth_token = self.db.execute(stmt).scalar_one_or_none()

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
            self.db.add(oauth_token)

    @staticmethod
    def _extract_expiration(token_info: dict[str, str]) -> datetime | None:
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
