"""
데이터 정리 서비스 (영구 삭제 스케줄러)
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.transaction_manager import TransactionManager
from app.models.ai_usage_log import AIUsageLog
from app.models.diary import DiaryEntry
from app.models.email_verification import EmailVerification
from app.models.emotion_stats import EmotionStats
from app.models.image import Image
from app.models.oauth_token import OAuthToken
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.schemas.cleanup import (
    CleanupExpiredSoftDeletedDataResponseData,
    GetSoftDeletedStatisticsResponseData,
)
from app.services.base import BaseService

logger = logging.getLogger(__name__)


class CleanupService(BaseService):
    """데이터 정리 서비스"""

    def __init__(self, db: Session):
        super().__init__(db)

    def cleanup_expired_soft_deleted_data(self):
        """
        30일 경과된 Soft Delete 데이터 영구 삭제

        Returns:
            삭제된 데이터 통계
        """
        with TransactionManager.transaction(self._db) as tx:
            cutoff_date = datetime.now() - timedelta(days=30)

            # 영구 삭제 대상 사용자 서브쿼리 (30일 경과 Soft Delete)
            users_to_delete_subq = select(User.id).where(
                User.deleted_at.is_not(None), User.deleted_at < cutoff_date
            )

            # 삭제 전 통계
            _delete_prev_user_count = tx.execute(
                select(func.count(User.id))
                .select_from(User)
                .where(User.deleted_at.is_not(None), User.deleted_at < cutoff_date)
            ).scalar_one()

            _delete_prev_diary_count = tx.execute(
                select(func.count(DiaryEntry.id))
                .select_from(DiaryEntry)
                .where(
                    DiaryEntry.deleted_at.is_not(None),
                    DiaryEntry.deleted_at < cutoff_date,
                )
            ).scalar_one()

            # 영구 삭제 실행 (FK 순서 준수: 가장 하위 → 상위)
            # 1) 이미지 삭제 (다이어리 기준)
            deleted_images = len(
                tx.execute(
                    delete(Image)
                    .where(
                        Image.diary_id.in_(
                            select(DiaryEntry.id).where(
                                (
                                    DiaryEntry.deleted_at.is_not(None)
                                    & (DiaryEntry.deleted_at < cutoff_date)
                                )
                                | (DiaryEntry.user_id.in_(users_to_delete_subq))
                            )
                        )
                    )
                    .returning(Image.id)
                )
                .scalars()
                .all()
            )

            # 2) 다이어리 삭제 (사용자 기준 포함)
            # PostgreSQL: DELETE ... RETURNING(id)로 실제 삭제된 다이어리 id들을 받아 정확한 개수 산출
            deleted_diaries = len(
                tx.execute(
                    delete(DiaryEntry)
                    .where(
                        (
                            DiaryEntry.deleted_at.is_not(None)
                            & (DiaryEntry.deleted_at < cutoff_date)
                        )
                        | (DiaryEntry.user_id.in_(users_to_delete_subq))
                    )
                    .returning(DiaryEntry.id)
                )
                .scalars()
                .all()
            )

            # 3) 사용자 종속 테이블 삭제 (CASCADE 미설정 테이블)
            deleted_ai_logs = len(
                tx.execute(
                    delete(AIUsageLog)
                    .where(AIUsageLog.user_id.in_(users_to_delete_subq))
                    .returning(AIUsageLog.id)
                )
                .scalars()
                .all()
            )

            deleted_oauth = len(
                tx.execute(
                    delete(OAuthToken)
                    .where(OAuthToken.user_id.in_(users_to_delete_subq))
                    .returning(OAuthToken.id)
                )
                .scalars()
                .all()
            )

            deleted_reset_tokens = len(
                tx.execute(
                    delete(PasswordResetToken)
                    .where(PasswordResetToken.user_id.in_(users_to_delete_subq))
                    .returning(PasswordResetToken.id)
                )
                .scalars()
                .all()
            )

            deleted_emotion_stats = len(
                tx.execute(
                    delete(EmotionStats)
                    .where(EmotionStats.user_id.in_(users_to_delete_subq))
                    .returning(EmotionStats.id)
                )
                .scalars()
                .all()
            )

            deleted_email_verifications = len(
                tx.execute(
                    delete(EmailVerification)
                    .where(EmailVerification.user_id.in_(users_to_delete_subq))
                    .returning(EmailVerification.id)
                )
                .scalars()
                .all()
            )

            # 4) 사용자 삭제 (최상위)
            deleted_users = len(
                tx.execute(
                    delete(User)
                    .where(User.id.in_(users_to_delete_subq))
                    .returning(User.id)
                )
                .scalars()
                .all()
            )

        # 로그 기록
        logger.info(
            "영구 삭제 완료: 사용자 %s, 다이어리 %s, 이미지 %s, oauth %s, reset_tokens %s, ai_logs %s, emotion_stats %s, email_verifications %s",
            deleted_users,
            deleted_diaries,
            deleted_images,
            deleted_oauth,
            deleted_reset_tokens,
            deleted_ai_logs,
            deleted_emotion_stats,
            deleted_email_verifications,
        )

        return CleanupExpiredSoftDeletedDataResponseData(
            deleted_users=deleted_users,
            deleted_diaries=deleted_diaries,
            deleted_images=deleted_images,
            deleted_oauth_tokens=deleted_oauth,
            deleted_password_reset_tokens=deleted_reset_tokens,
            deleted_ai_usage_logs=deleted_ai_logs,
            deleted_emotion_stats=deleted_emotion_stats,
            deleted_email_verifications=deleted_email_verifications,
            cutoff_date=cutoff_date.isoformat(),
            message=(
                "30일 경과 데이터 영구 삭제 완료: "
                f"사용자 {deleted_users}개, 다이어리 {deleted_diaries}개, 이미지 {deleted_images}개"
            ),
        )

    def get_soft_deleted_statistics(self):
        """
        Soft Delete된 데이터 통계 조회

        Returns:
            Soft Delete 데이터 통계
        """
        current_time = datetime.now()
        thirty_days_ago = current_time - timedelta(days=30)

        # 30일 이내 Soft Delete된 데이터
        recent_users = self._db.execute(
            select(func.count(User.id))
            .select_from(User)
            .where(User.deleted_at.is_not(None), User.deleted_at >= thirty_days_ago)
        ).scalar_one()

        recent_diaries = self._db.execute(
            select(func.count(DiaryEntry.id))
            .select_from(DiaryEntry)
            .where(
                DiaryEntry.deleted_at.is_not(None),
                DiaryEntry.deleted_at >= thirty_days_ago,
            )
        ).scalar_one()

        # 30일 경과된 데이터
        expired_users = self._db.execute(
            select(func.count(User.id))
            .select_from(User)
            .where(User.deleted_at.is_not(None), User.deleted_at < thirty_days_ago)
        ).scalar_one()

        expired_diaries = self._db.execute(
            select(func.count(DiaryEntry.id))
            .select_from(DiaryEntry)
            .where(
                DiaryEntry.deleted_at.is_not(None),
                DiaryEntry.deleted_at < thirty_days_ago,
            )
        ).scalar_one()

        return GetSoftDeletedStatisticsResponseData(
            recent_users=recent_users,
            recent_diaries=recent_diaries,
            expired_users=expired_users,
            expired_diaries=expired_diaries,
            total_soft_deleted_users=recent_users + expired_users,
            total_soft_deleted_diaries=recent_diaries + expired_diaries,
        )
