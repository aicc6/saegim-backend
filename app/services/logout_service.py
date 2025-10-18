import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.oauth_token import OAuthToken

logger = logging.getLogger(__name__)


class LogoutService:
    """로그아웃 서비스"""

    def __init__(self, db: Session):
        self._db = db

    async def revoke_google_token(self, access_token: str) -> bool:
        """구글 OAuth 토큰 무효화"""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    data={"token": access_token},
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Google token revocation failed: {e}")
            return False

    def invalidate_oauth_tokens(self, user_id: str) -> None:
        """사용자의 OAuth 토큰들을 무효화"""
        try:
            # 사용자의 OAuth 토큰 조회
            stmt = select(OAuthToken).where(OAuthToken.user_id == user_id)
            result = self._db.execute(stmt)
            oauth_tokens = result.scalars().all()

            for oauth_token in oauth_tokens:
                # 토큰 만료 시간을 현재 시간으로 설정하여 무효화
                oauth_token.expires_at = datetime.now(UTC)

            self._db.commit()
            logger.info(
                f"Invalidated {len(oauth_tokens)} OAuth tokens for user {user_id}"
            )

        except Exception as e:
            logger.error(f"Failed to invalidate OAuth tokens for user {user_id}: {e}")
            self._db.rollback()

    def log_logout_attempt(
        self, user_id: str, success: bool, details: str = ""
    ) -> None:
        """로그아웃 시도 기록"""
        try:
            log_message = f"Logout attempt - User: {user_id}, Success: {success}"
            if details:
                log_message += f", Details: {details}"

            if success:
                logger.info(log_message)
            else:
                logger.warning(log_message)

        except Exception as e:
            logger.error(f"Failed to log logout attempt: {e}")
