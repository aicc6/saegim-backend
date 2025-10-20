"""
의존성 주입 (Dependency Injection)
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import AuthConstants, ResponseMessages
from app.core.config import get_settings
from app.core.security import (
    JWTHandler,
    get_current_user_id_from_cookie,
)
from app.db.database import get_session
from app.models.user import User
from app.services.ai_service import AIService
from app.services.app_version_service import AppVersionService
from app.services.auth_service import AuthService
from app.services.cleanup_service import CleanupService
from app.services.create_diary import CreateAIUsageLogService
from app.services.diary import DiaryService
from app.services.minio_service import MinioService, get_minio_service
from app.services.notification_service import NotificationService
from app.services.oauth import GoogleOAuthService
from app.services.support_service import SupportService
from app.utils.email_service import EmailService
from app.utils.fcm_push import FCMPushService, get_fcm_service

logger = logging.getLogger(__name__)

settings = get_settings()
security = HTTPBearer()


DbSession = Annotated[Session, Depends(get_session)]


async def get_current_user_id(request: Request):
    """
    쿠키 또는 Bearer 토큰을 통해 현재 로그인한 사용자 ID 조회
    (소셜 로그인: 쿠키, 이메일 로그인: Bearer 토큰)

    Args:
        request: FastAPI Request 객체

    Returns:
        현재 로그인한 사용자 ID

    Raises:
        HTTPException: 토큰이 유효하지 않은 경우
    """

    try:
        # 쿠키 존재 여부만 확인 (보안상 키 목록은 로깅하지 않음)
        has_cookies = bool(request.cookies)
        logger.debug(f"쿠키 존재 여부: {has_cookies}")

        user_id = await _extract_user_id(request)

        if user_id is None:
            logger.error("인증 토큰을 찾을 수 없음")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseMessages.TOKEN_REQUIRED,
            )

        return user_id

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"인증 중 예외 발생: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ResponseMessages.AUTH_FAILED,
        )


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


async def _extract_user_id(request: Request) -> UUID | None:
    """쿠키 또는 Bearer 토큰에서 사용자 ID 추출"""
    logger.debug("사용자 ID 추출 시작")

    try:
        # 1. 쿠키에서 토큰 확인 (소셜 로그인)
        logger.debug("쿠키에서 토큰 추출 시도")
        user_id = get_current_user_id_from_cookie(request)
        logger.debug("쿠키에서 user_id 추출 성공")
        return user_id
    except HTTPException as e:
        logger.debug("쿠키 인증 실패")
    except Exception as e:
        logger.error(f"쿠키 인증 중 예상치 못한 오류: {e}")
        pass

    # 2. Authorization 헤더에서 토큰 확인 (이메일 로그인)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith(AuthConstants.BEARER_PREFIX):
        token = auth_header.split(" ")[1]
        payload = JWTHandler.decode_token(token)
        sub = payload.get("sub")
        assert sub is not None, "토큰에 사용자 ID(sub)가 포함되어 있지 않음"
        logger.debug("Bearer 토큰에서 user_id 추출 성공")
        return UUID(sub)

    return None


async def _validate_user(user_id: UUID, db: Session) -> User:
    """사용자 존재 여부 및 활성 상태 확인"""
    logger.debug("사용자 검증 시작")

    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    result = db.execute(stmt)
    user = result.scalar_one_or_none()

    logger.info(f"데이터베이스 조회 결과: {'사용자 존재' if user else '사용자 없음'}")

    if user is None:
        logger.error(f"사용자를 찾을 수 없음: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ResponseMessages.USER_NOT_FOUND,
        )

    if not user.is_active:
        logger.error(f"비활성화된 계정: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ResponseMessages.ACCOUNT_INACTIVE,
        )

    return user


async def get_current_user(
    request: Request, db: Session = Depends(get_session)
) -> User:
    """
    쿠키 또는 Bearer 토큰을 통해 현재 로그인한 사용자 조회
    (소셜 로그인: 쿠키, 이메일 로그인: Bearer 토큰)

    Args:
        request: FastAPI Request 객체
        db: 데이터베이스 세션

    Returns:
        현재 로그인한 사용자

    Raises:
        HTTPException: 토큰이 유효하지 않은 경우
    """
    try:
        user_id = await _extract_user_id(request)

        if user_id is None:
            logger.error("인증 토큰을 찾을 수 없음")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ResponseMessages.TOKEN_REQUIRED,
            )

        user = await _validate_user(user_id, db)
        logger.info(f"인증 성공: {user_id}")
        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"인증 중 예외 발생: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ResponseMessages.AUTH_FAILED,
        )


CurrentUser = Annotated[User, Depends(get_current_user)]


# Services
def email_service():
    return EmailService()


EmailServiceDep = Annotated[EmailService, Depends(email_service)]


def support_service(email_service: EmailServiceDep):
    return SupportService(email_service)


SupportServiceDep = Annotated[SupportService, Depends(support_service)]

FcmServiceDep = Annotated[FCMPushService, Depends(get_fcm_service)]


def notification_service(db: DbSession, fcm_service: FcmServiceDep):
    return NotificationService(db, fcm_service)


NotificationServiceDep = Annotated[NotificationService, Depends(notification_service)]


def cleanup_service(db: DbSession):
    return CleanupService(db)


CleanupServiceDep = Annotated[CleanupService, Depends(cleanup_service)]


def google_oauth_service(db: DbSession):
    return GoogleOAuthService(db)


GoogleOAuthServiceDep = Annotated[GoogleOAuthService, Depends(google_oauth_service)]


def auth_service(
    db: DbSession,
    email_service: EmailServiceDep,
    google_oauth_service: GoogleOAuthServiceDep,
):
    return AuthService(db, email_service, google_oauth_service)


AuthServiceDep = Annotated[AuthService, Depends(auth_service)]


def create_ai_usage_log_service(db: DbSession):
    return CreateAIUsageLogService(db)


CreateAIUsageLogServiceDep = Annotated[
    CreateAIUsageLogService, Depends(create_ai_usage_log_service)
]


def ai_service(db: DbSession):
    return AIService(db)


AIServiceDep = Annotated[AIService, Depends(ai_service)]


def diary_service(db: DbSession):
    return DiaryService(db)


DiaryServiceDep = Annotated[DiaryService, Depends(diary_service)]

MinioServiceDep = Annotated[MinioService, Depends(get_minio_service)]


def app_version_service(db: DbSession, minio_service: MinioServiceDep):
    return AppVersionService(db, minio_service)


AppVersionServiceDep = Annotated[AppVersionService, Depends(app_version_service)]
