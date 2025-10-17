"""
AI 사용 로그 생성 서비스
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.transaction_manager import TransactionManager
from app.models.ai_usage_log import AIUsageLog
from app.schemas.ai import CreateAiUsageLogRequest, CreateAiUsageLogResponseData
from app.services.base import BaseService

logger = logging.getLogger(__name__)


class CreateAIUsageLogService(BaseService):
    """AI 사용 로그 생성 서비스 클래스"""

    def __init__(self, db: Session):
        super().__init__(db)

    async def create_ai_usage_log(
        self,
        user_id: UUID,
        request: CreateAiUsageLogRequest,
    ):
        """
        AI 사용 로그를 생성합니다.

        Args:
            user_id: 사용자 ID (UUID 문자열)
            request: CreateAiUsageLogRequest

        Returns:
            생성된 AI 사용 로그

        Raises:
            ValueError: 사용자를 찾을 수 없거나 데이터 검증 실패 시
            SQLAlchemyError: 데이터베이스 오류 시
        """
        with TransactionManager.transaction(self._db) as tx:
            # AI 사용 로그 생성
            ai_usage_log = AIUsageLog(
                user_id=user_id,
                api_type=request.api_type,
                session_id=request.session_id,
                regeneration_count=request.regeneration_count,
                tokens_used=request.tokens_used,
                request_data=request.request_data,
                response_data=request.response_data,
            )

            # 데이터베이스에 저장
            tx.add(ai_usage_log)

        logger.info(
            f"AI 사용 로그 생성 성공: user_id={user_id}, log_id={ai_usage_log.id}"
        )

        return CreateAiUsageLogResponseData.model_validate(ai_usage_log)

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
