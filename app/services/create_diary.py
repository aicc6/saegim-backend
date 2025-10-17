"""
AI 사용 로그 생성 서비스
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai_usage_log import AIUsageLog
from app.models.user import User
from app.services.base import BaseService

logger = logging.getLogger(__name__)


class CreateAIUsageLogService(BaseService):
    """AI 사용 로그 생성 서비스 클래스"""

    def __init__(self, db: Session):
        super().__init__(db)

    async def create_ai_usage_log(
        self,
        user_id: UUID,
        api_type: str,
        session_id: str,
        regeneration_count: int = 1,
        tokens_used: int = 0,
        request_data: dict[str, Any] | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> AIUsageLog:
        """
        AI 사용 로그를 생성합니다.

        Args:
            user_id: 사용자 ID (UUID 문자열)
            api_type: API 타입 (generate/keywords)
            session_id: 재생성 세션 ID
            regeneration_count: 현재 재생성 횟수 (1-5)
            tokens_used: 사용된 토큰 수
            request_data: 요청 데이터
            response_data: 응답 데이터

        Returns:
            생성된 AI 사용 로그

        Raises:
            ValueError: 사용자를 찾을 수 없거나 데이터 검증 실패 시
            SQLAlchemyError: 데이터베이스 오류 시
        """
        # 사용자 ID 검증 및 조회
        user = await self._get_user_by_id(user_id)
        if not user:
            raise ValueError("사용자를 찾을 수 없습니다.")

        # 데이터 검증
        self._validate_log_data(api_type, regeneration_count)

        # AI 사용 로그 생성
        ai_usage_log = await self._create_ai_usage_log_entry(
            user.id,
            api_type,
            session_id,
            regeneration_count,
            tokens_used,
            request_data or {},
            response_data or {},
        )

        logger.info(
            f"AI 사용 로그 생성 성공: user_id={user.id}, log_id={ai_usage_log.id}"
        )
        return ai_usage_log

    async def _get_user_by_id(self, user_id: UUID) -> User | None:
        """사용자 ID로 사용자 정보를 조회합니다."""
        try:
            # 사용자 정보 조회
            query = select(User).where(User.id == user_id)
            result = self._db.execute(query)
            user = result.scalar_one_or_none()

            if not user:
                logger.warning(f"사용자 ID로 사용자를 찾을 수 없음: {user_id}")
                return None

            return user

        except Exception as e:
            logger.error(f"사용자 조회 중 오류 발생: {e}")
            return None

    def _validate_log_data(self, api_type: str, regeneration_count: int) -> None:
        """로그 데이터를 검증합니다."""
        settings = get_settings()

        # API 타입 검증
        if api_type not in ["generate", "keywords"]:
            raise ValueError(
                "유효하지 않은 API 타입입니다. 'generate' 또는 'keywords'여야 합니다."
            )

        # 재생성 횟수 검증
        if not (1 <= regeneration_count <= settings.ai_max_regeneration_count):
            raise ValueError(
                f"재생성 횟수는 1-{settings.ai_max_regeneration_count} 범위 내여야 합니다."
            )

    async def _create_ai_usage_log_entry(
        self,
        user_id: UUID,
        api_type: str,
        session_id: str,
        regeneration_count: int,
        tokens_used: int,
        request_data: dict[str, Any],
        response_data: dict[str, Any],
    ) -> AIUsageLog:
        """데이터베이스에 AI 사용 로그 엔트리를 생성합니다."""
        try:
            # 새로운 AI 사용 로그 엔트리 생성
            ai_usage_log = AIUsageLog(
                user_id=user_id,
                api_type=api_type,
                session_id=session_id,
                regeneration_count=regeneration_count,
                tokens_used=tokens_used,
                request_data=request_data,
                response_data=response_data,
            )

            # 데이터베이스에 저장
            self._db.add(ai_usage_log)
            self._db.commit()
            self._db.refresh(ai_usage_log)

            return ai_usage_log

        except Exception as e:
            self._db.rollback()
            logger.error(f"AI 사용 로그 엔트리 생성 중 오류 발생: {e}")
            raise


# diary_service 객체 생성 (기존 코드와의 호환성을 위해 이름 유지)
# 실제 사용 시에는 db 세션을 전달해야 합니다
diary_service = CreateAIUsageLogService
