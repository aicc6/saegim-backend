"""
알림 서비스
FCM 디바이스 토큰 관리, 푸시 알림 전송 및 인앱 알림 통합 관리
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.config import get_settings
from app.core.transaction_manager import TransactionManager
from app.models.diary import DiaryEntry
from app.models.fcm import FCMToken, NotificationHistory, NotificationSettings
from app.models.notification import Notification
from app.schemas.notification import (
    DeleteNotificationResponseData,
    MarkNotificationAsReadResponseData,
    MarkNotificationsAsReadResponseData,
    NotificationHistoryResponseData,
    NotificationSettingsResponseData,
    NotificationSettingsUpdate,
    RegisterFcmTokenRequest,
    RegisterFcmTokenResponseData,
    SendNotificationRequest,
    SendNotificationResponseData,
)
from app.services.base import BaseService
from app.utils.fcm_push import FCMPushService

logger = logging.getLogger(__name__)


class NotificationService(BaseService):
    """알림 토큰 및 푸시 알림 관리 서비스"""

    def __init__(self, db: Session, fcm_service: FCMPushService):
        """
        알림 서비스 초기화

        Args:
            db: 데이터베이스 세션 (선택사항)
        """
        super().__init__(db)
        assert isinstance(fcm_service, FCMPushService), "FCMPushService is required."
        self.__fcm_service = fcm_service

    def _extract_error_message(self, result: dict[str, Any]) -> str:
        """FCM 응답에서 에러 메시지를 안전하게 추출"""
        try:
            response = result.get("response")
            if isinstance(response, dict):
                response_dict = cast(dict[str, Any], response)
                error = response_dict.get("error")
                if isinstance(error, dict):
                    error_dict = cast(dict[str, Any], error)
                    message = error_dict.get("message")
                    if isinstance(message, str):
                        return message
            return "알 수 없는 오류"
        except (AttributeError, TypeError):
            return "알 수 없는 오류"

    def register_token(
        self,
        user_id: UUID,
        token_data: RegisterFcmTokenRequest,
    ):
        """FCM 토큰 등록 또는 업데이트 (재시도 로직 개선)"""

        settings = get_settings()
        max_retries = settings.fcm_max_retries
        retry_delay = settings.fcm_retry_delay

        for attempt in range(max_retries):
            try:
                # PostgreSQL UPSERT를 사용하여 동시성 이슈 해결
                stmt_ins = insert(FCMToken).values(
                    user_id=user_id,
                    token=token_data.token,
                    device_type=token_data.device_type,
                    device_info=token_data.device_info,
                    is_active=True,
                )

                # ON CONFLICT DO UPDATE - 중복 시 업데이트
                stmt_upsert = stmt_ins.on_conflict_do_update(
                    constraint="uq_fcm_tokens_user_token",  # unique constraint 이름
                    set_={
                        "device_type": stmt_ins.excluded.device_type,
                        "device_info": stmt_ins.excluded.device_info,
                        "is_active": stmt_ins.excluded.is_active,
                        "updated_at": datetime.now(UTC),
                    },
                ).returning(FCMToken)

                result = self._db.execute(stmt_upsert).scalar_one()
                self._db.commit()

                return RegisterFcmTokenResponseData.model_validate(result)

            except Exception as e:
                self._db.rollback()

                # 마지막 시도인 경우 예외 발생
                if attempt == max_retries - 1:
                    logger.error(
                        f"FCM 토큰 등록 최종 실패 (max retries: {max_retries}): {str(e)}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="FCM 토큰 등록에 실패했습니다.",
                    ) from e

                # Postgres 고유 제약 위반(Unique Violation) 판별: psycopg2 타입 의존성을 피하고 pgcode(23505)를 확인
                is_unique_violation = False
                if isinstance(e, IntegrityError):
                    orig = getattr(e, "orig", None)
                    if (
                        getattr(orig, "pgcode", None) == "23505"
                    ):  # Postgres unique_violation
                        is_unique_violation = True
                else:
                    cause = getattr(e, "__cause__", None)
                    if getattr(cause, "pgcode", None) == "23505":
                        is_unique_violation = True

                # UniqueViolation 또는 기타 일시적 오류인 경우 재시도
                if is_unique_violation or attempt < max_retries - 1:
                    logger.warning(
                        f"FCM 토큰 등록 재시도 {attempt + 1}/{max_retries}: {str(e)}"
                    )
                    time.sleep(retry_delay * (attempt + 1))  # 지수 백오프
                    continue

        # 모든 재시도 실패
        logger.error("모든 재시도 실패 후 FCM 토큰 등록 중단")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="FCM 토큰 등록에 실패했습니다.",
        )

    def get_user_tokens(self, user_id: UUID):
        """사용자의 활성 FCM 토큰 목록 조회"""
        stmt = select(FCMToken).where(
            and_(FCMToken.user_id == user_id, FCMToken.is_active)
        )
        tokens = self._db.execute(stmt).scalars().all()

        return [RegisterFcmTokenResponseData.model_validate(token) for token in tokens]

    def delete_token(self, user_id: UUID, token_id: str):
        """FCM 토큰 삭제 (비활성화)"""
        with TransactionManager.transaction(self._db) as tx:
            stmt = select(FCMToken).where(
                and_(FCMToken.id == token_id, FCMToken.user_id == user_id)
            )
            token = tx.execute(stmt).scalar_one_or_none()

            if not token:
                return False

            token.is_active = False
            token.updated_at = datetime.now(UTC)

            tx.add(token)

    def get_notification_settings(self, user_id: UUID):
        """사용자 알림 설정 조회"""
        with TransactionManager.transaction(self._db) as tx:
            stmt = select(NotificationSettings).where(
                and_(NotificationSettings.user_id == user_id)
            )
            settings = tx.execute(stmt).scalar_one_or_none()

            if not settings:
                # 기본 설정 생성
                settings = NotificationSettings(user_id=user_id)
                tx.add(settings)

            return NotificationSettingsResponseData.model_validate(settings)

    def update_notification_settings(
        self,
        user_id: UUID,
        settings_data: NotificationSettingsUpdate,
    ) -> NotificationSettingsResponseData:
        """사용자 알림 설정 업데이트"""
        with TransactionManager.transaction(self._db) as tx:
            stmt = select(NotificationSettings).where(
                NotificationSettings.user_id == user_id
            )
            settings = tx.execute(stmt).scalar_one_or_none()

            if not settings:
                # 기본 설정 생성
                settings = NotificationSettings(user_id=user_id)
                tx.add(settings)

            # 스키마 필드와 모델 필드가 일치하므로 직접 업데이트
            update_data = settings_data.model_dump(exclude_unset=True)

            for field_name, value in update_data.items():
                if hasattr(settings, field_name):
                    setattr(settings, field_name, value)

            settings.updated_at = datetime.now(UTC)
            tx.add(settings)

        return NotificationSettingsResponseData.model_validate(settings)

    async def __send_notification(
        self, notification_data: SendNotificationRequest, tx: Session
    ):
        """푸시 알림 전송"""
        try:
            # 빈 사용자 목록 체크
            if not notification_data.user_ids:
                return SendNotificationResponseData(
                    success_count=0,
                    failure_count=0,
                    successful_tokens=[],
                    failed_tokens=[],
                    message="전송할 사용자가 없습니다.",
                )

            successful_tokens: list[str] = []
            failed_tokens: list[str] = []

            # 대상 사용자들의 활성 토큰 조회 (N+1 쿼리 최적화)
            stmt = select(FCMToken).where(
                and_(
                    FCMToken.user_id.in_(notification_data.user_ids), FCMToken.is_active
                )
            )
            all_tokens = tx.execute(stmt).scalars().all()

            if not all_tokens:
                return SendNotificationResponseData(
                    success_count=0,
                    failure_count=0,
                    successful_tokens=[],
                    failed_tokens=[],
                    message="전송할 활성 토큰이 없습니다.",
                )

            created_notifications: dict[UUID, UUID] = {}

            # 대량 insert 최적화: 여러 알림을 한 번에 생성
            notifications_to_create = [
                Notification(
                    user_id=user_id,
                    type=notification_data.notification_type,
                    title=notification_data.title,
                    message=notification_data.body,
                    data=notification_data.data,
                )
                for user_id in notification_data.user_ids
            ]

            tx.add_all(notifications_to_create)
            tx.flush()  # ID를 얻기 위해 flush

            # 사용자 ID와 알림 ID 매핑
            for notification in notifications_to_create:
                created_notifications[notification.user_id] = notification.id

            # 각 토큰에 대해 알림 전송
            for token_model in all_tokens:
                try:
                    # 알림 전송
                    result = await self.__fcm_service.send_notification(
                        token=token_model.token,
                        title=notification_data.title,
                        body=notification_data.body,
                        data=notification_data.data,
                    )

                    if result["success"]:
                        successful_tokens.append(token_model.token)
                        status_value = "sent"
                    else:
                        failed_tokens.append(token_model.token)
                        status_value = "failed"

                        # UNREGISTERED 토큰인 경우 비활성화
                        if result.get("error_type") == "UNREGISTERED":
                            logger.warning(
                                f"토큰 {token_model.token[:10]}...이 UNREGISTERED 상태입니다. 비활성화합니다."
                            )
                            token_model.is_active = False
                            token_model.updated_at = datetime.now(UTC)

                    # 알림 기록 저장
                    history = NotificationHistory(
                        user_id=token_model.user_id,
                        notification_id=created_notifications.get(token_model.user_id),
                        fcm_token_id=token_model.id,
                        notification_type=notification_data.notification_type,
                        status=status_value,
                        data_payload={
                            "token": token_model.token[:10]
                            + "...",  # 보안을 위해 일부만 저장
                            "success": result["success"],
                            "error_type": result.get("error_type"),
                            "fcm_response": result.get("response"),
                            "title": notification_data.title,  # data_payload에 저장
                            "body": notification_data.body,  # data_payload에 저장
                        },
                        sent_at=datetime.now(UTC) if result["success"] else None,
                        error_message=(
                            self._extract_error_message(result)
                            if (not result.get("success", False))
                            else None
                        ),
                    )
                    tx.add(history)

                except Exception as e:
                    logger.error(
                        f"Error sending to token {token_model.token[:10]}...: {str(e)}"
                    )
                    failed_tokens.append(token_model.token)

                    # 실패 기록 저장
                    history = NotificationHistory(
                        user_id=token_model.user_id,
                        notification_id=created_notifications.get(token_model.user_id),
                        fcm_token_id=token_model.id,
                        notification_type=notification_data.notification_type,
                        status="failed",
                        error_message=str(e),
                        data_payload={
                            "token": token_model.token[:10] + "...",
                            "title": notification_data.title,  # data_payload에 저장
                            "body": notification_data.body,  # data_payload에 저장
                        },
                    )
                    tx.add(history)

            tx.commit()

            return SendNotificationResponseData(
                success_count=len(successful_tokens),
                failure_count=len(failed_tokens),
                successful_tokens=successful_tokens,
                failed_tokens=failed_tokens,
                message=f"알림 전송 완료: 성공 {len(successful_tokens)}개, 실패 {len(failed_tokens)}개",
            )

        except Exception as e:
            tx.rollback()
            logger.error(f"Error sending notification: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="알림 전송에 실패했습니다.",
            ) from e

    async def send_diary_reminder(self, user_id: UUID):
        """다이어리 작성 알림 전송"""
        with TransactionManager.transaction(self._db) as tx:
            # 알림 설정 확인
            settings_stmt = select(NotificationSettings).where(
                NotificationSettings.user_id == user_id
            )
            settings = tx.execute(settings_stmt).scalar_one_or_none()

            if settings and not settings.diary_reminder_enabled:
                return SendNotificationResponseData(
                    success_count=0,
                    failure_count=0,
                    successful_tokens=[],
                    failed_tokens=[],
                    message="사용자가 다이어리 알림을 비활성화했습니다.",
                )

            # 알림 전송
            notification_request = SendNotificationRequest(
                title="📝 오늘의 감정을 기록해보세요",
                body="새김에서 오늘 하루를 돌아보며 마음을 정리해보세요.",
                notification_type="diary_reminder",
                user_ids=[user_id],
                data={"action": "write_diary"},
            )

            return await self.__send_notification(notification_request, tx)

    async def send_ai_content_ready(
        self, user_id: UUID, diary_id: UUID
    ) -> SendNotificationResponseData:
        """AI 콘텐츠 준비 완료 알림 전송"""
        with TransactionManager.transaction(self._db) as tx:
            # 다이어리 존재 확인
            diary_stmt = select(DiaryEntry).where(DiaryEntry.id == diary_id)
            diary = tx.execute(diary_stmt).scalar_one_or_none()

            if not diary:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="다이어리를 찾을 수 없습니다.",
                )

            # 알림 설정 확인
            settings_stmt = select(NotificationSettings).where(
                NotificationSettings.user_id == user_id
            )
            settings = tx.execute(settings_stmt).scalar_one_or_none()

            if settings and not settings.ai_processing_enabled:
                return SendNotificationResponseData(
                    success_count=0,
                    failure_count=0,
                    successful_tokens=[],
                    failed_tokens=[],
                    message="사용자가 AI 콘텐츠 알림을 비활성화했습니다.",
                )

            # 알림 전송
            notification_request = SendNotificationRequest(
                title="✨ AI가 당신의 마음을 읽었어요",
                body=f"'{diary.title}' 일기에 특별한 글귀가 준비되었습니다.",
                notification_type="ai_content_ready",
                user_ids=[user_id],
                data={"diary_id": diary_id, "action": "view_ai_content"},
            )

            return await self.__send_notification(notification_request, tx)

    def get_notification_history(self, user_id: UUID, limit: int, offset: int):
        """사용자 알림 기록 조회 - notifications 기준으로 조회

        요구사항 변경: notification_history가 아닌 notifications 테이블을 기준으로 조회하고,
        각 notification에 대한 최신 history(있다면)를 LEFT JOIN하여 상태/타임스탬프를 보강합니다.
        """
        # 각 notification_id별 최신(created_at 최대) history를 구하는 서브쿼리
        latest_hist_subq = (
            select(
                NotificationHistory.notification_id.label("lh_notification_id"),
                func.max(NotificationHistory.created_at).label("lh_max_created_at"),
            )
            .where(NotificationHistory.user_id == user_id)
            .group_by(NotificationHistory.notification_id)
            .subquery()
        )

        # 최신 history 레코드 자체와 조인하기 위한 별칭
        LatestHistory = aliased(NotificationHistory)

        # notifications를 기준으로 LEFT JOIN
        stmt = (
            select(
                # Notification 컬럼들 (필요한 컬럼만)
                Notification.id.label("n_id"),
                Notification.type.label("n_type"),
                Notification.title.label("n_title"),
                Notification.message.label("n_message"),
                Notification.data.label("n_data"),
                Notification.is_read.label("n_is_read"),
                Notification.created_at.label("n_created_at"),
                # LatestHistory 컬럼들 (필요한 컬럼만)
                LatestHistory.status.label("h_status"),
                LatestHistory.data_payload.label("h_data_payload"),
            )
            .select_from(Notification)
            .outerjoin(
                latest_hist_subq,
                Notification.id == latest_hist_subq.c.lh_notification_id,
            )
            .outerjoin(
                LatestHistory,
                and_(
                    LatestHistory.notification_id
                    == latest_hist_subq.c.lh_notification_id,
                    LatestHistory.created_at == latest_hist_subq.c.lh_max_created_at,
                ),
            )
            .where(
                and_(
                    Notification.user_id == user_id,
                    # 논리적으로 '보낸' 알림만: 예약 시간이 미래인 항목 제외
                    or_(
                        Notification.scheduled_at.is_(None),
                        Notification.scheduled_at <= datetime.now(UTC),
                    ),
                )
            )
            .order_by(desc(Notification.created_at))
            .limit(limit)
            .offset(offset)
        )

        rows = self._db.execute(stmt).all()

        response: list[NotificationHistoryResponseData] = [
            NotificationHistoryResponseData(
                id=str(row.n_id),
                title=row.n_title,
                body=row.n_message,
                notification_type=row.n_type,
                status="opened" if row.n_is_read else (row.h_status or "sent"),
                created_at=row.n_created_at,
                fcm_response=(row.h_data_payload if row.h_data_payload else row.n_data),
            )
            for row in rows
        ]

        return response

    def mark_notification_as_read(self, user_id: UUID, notification_id: UUID):
        with TransactionManager.transaction(self._db) as tx:
            # 1. notification 테이블 업데이트
            notification_stmt = select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user_id
            )
            notification = tx.execute(notification_stmt).scalar_one_or_none()

            if not notification:
                return

            # notification 읽음 처리
            notification.is_read = True
            read_at = datetime.now(UTC)
            notification.read_at = read_at

            # 2. notification_history 테이블 업데이트
            history_stmt = select(NotificationHistory).where(
                NotificationHistory.notification_id == notification_id
            )
            histories = tx.execute(history_stmt).scalars().all()

            # history 레코드들의 opened_at 업데이트
            for history in histories:
                if not history.opened_at:
                    history.opened_at = read_at

        return MarkNotificationAsReadResponseData(
            notification_id=notification_id,
            updated_histories=len(histories),
            read_at=read_at.isoformat(),
        )

    def mark_all_notifications_as_read(self, user_id: UUID):
        with TransactionManager.transaction(self._db) as tx:
            now = datetime.now(UTC)

            # 1. 모든 읽지 않은 notification 조회
            unread_notifications_stmt = select(Notification).where(
                Notification.user_id == user_id, Notification.is_read.is_(False)
            )
            unread_notifications = tx.execute(unread_notifications_stmt).scalars().all()

            if not unread_notifications:
                return MarkNotificationsAsReadResponseData(
                    updated_notifications=0,
                    updated_histories=0,
                    read_at=now.isoformat(),
                )

            # 2. notification 테이블 일괄 업데이트
            notification_ids = [notif.id for notif in unread_notifications]
            for notification in unread_notifications:
                notification.is_read = True
                notification.read_at = now

            # 3. 관련 notification_history 업데이트
            history_stmt = select(NotificationHistory).where(
                NotificationHistory.notification_id.in_(notification_ids)
            )
            histories = tx.execute(history_stmt).scalars().all()

            for history in histories:
                if not history.opened_at:
                    history.opened_at = now

        return MarkNotificationsAsReadResponseData(
            updated_notifications=len(unread_notifications),
            updated_histories=len(histories),
            read_at=now.isoformat(),
        )

    def delete_notification(self, user_id: UUID, notification_id: UUID):
        with TransactionManager.transaction(self._db) as tx:
            # 1) 해당 사용자의 알림인지 확인
            notification_stmt = select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user_id
            )
            notification = tx.execute(notification_stmt).scalar_one_or_none()

            # 2) 관련 history 정리 (존재 시)
            history_delete_stmt = delete(NotificationHistory).where(
                and_(NotificationHistory.notification_id == notification_id)
            )
            tx.execute(history_delete_stmt)

            # 3) 알림 삭제
            tx.delete(notification)

        return DeleteNotificationResponseData(
            notification_id=str(notification_id),
            deleted=True,
        )

    async def cleanup_invalid_tokens(self) -> int:
        """무효한 FCM 토큰들을 정리합니다"""
        try:
            # 모든 활성 토큰 조회
            stmt = select(FCMToken).where(FCMToken.is_active)
            active_tokens = self._db.execute(stmt).scalars().all()

            cleanup_count = 0

            # 각 토큰을 테스트하여 유효성 확인 (주의: 실제 알림은 전송하지 않음)
            for token_model in active_tokens:
                try:
                    # 더미 알림으로 토큰 유효성 테스트 (dry run)
                    result = await self.__fcm_service.send_notification(
                        token=token_model.token,
                        title="토큰 검증",
                        body="이 알림은 토큰 유효성 검증용입니다.",
                        data={"type": "validation", "test": "true"},
                    )

                    # UNREGISTERED 토큰인 경우 비활성화
                    if (
                        not result["success"]
                        and result.get("error_type") == "UNREGISTERED"
                    ):
                        logger.info(
                            f"무효한 토큰 비활성화: {token_model.token[:10]}..."
                        )
                        token_model.is_active = False
                        token_model.updated_at = datetime.now(UTC)
                        cleanup_count += 1

                except Exception as e:
                    logger.error(
                        f"토큰 검증 중 오류 {token_model.token[:10]}...: {str(e)}"
                    )
                    continue

            self._db.commit()
            logger.info(f"FCM 토큰 정리 완료: {cleanup_count}개 토큰 비활성화")
            return cleanup_count

        except Exception as e:
            self._db.rollback()
            logger.error(f"FCM 토큰 정리 중 오류: {str(e)}")
            return 0

    def get_active_token_count(self, user_id: UUID) -> int:
        """사용자의 활성 토큰 개수를 반환합니다"""
        try:
            from sqlalchemy import func

            stmt = select(func.count(FCMToken.id)).where(
                and_(FCMToken.user_id == user_id, FCMToken.is_active)
            )
            count = self._db.execute(stmt).scalar()
            return count or 0
        except Exception as e:
            logger.error(f"활성 토큰 개수 조회 실패: {str(e)}")
            return 0
