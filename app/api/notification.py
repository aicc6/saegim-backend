"""
알림 시스템 API 라우터
FCM 푸시 알림, 인앱 알림 관리 및 읽음 처리 통합 API
"""

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUserId, DbSession
from app.schemas.base import StringResponse
from app.schemas.notification import (
    DeleteNotificationResponse,
    GetFcmTokensResponse,
    MarkNotificationAsReadResponse,
    MarkNotificationsAsReadResponse,
    NotificationHistoryResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    RegisterFcmTokenRequest,
    RegisterFcmTokenResponse,
    SendNotificationResponse,
)
from app.services.notification_service import NotificationService
from app.utils.fcm_push import get_fcm_service

# Protected endpoints (auth required)
router = APIRouter(tags=["Notifications"])


# ==================== FCM 토큰 관리 ====================
@router.post(
    "/tokens",
    response_model=RegisterFcmTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="FCM 토큰 등록",
    description="새로운 FCM 토큰을 등록하거나 기존 토큰을 업데이트합니다.",
)
def register_fcm_token(
    db: DbSession,
    user_id: CurrentUserId,
    token_data: RegisterFcmTokenRequest,
):
    """FCM 토큰 등록"""
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    data = notification_service.register_token(user_id, token_data)

    return RegisterFcmTokenResponse(
        data=data,
        message="FCM 토큰이 성공적으로 등록되었습니다.",
    )


@router.get(
    "/tokens",
    response_model=GetFcmTokensResponse,
    summary="FCM 토큰 목록 조회",
    description="현재 사용자의 활성 FCM 토큰 목록을 조회합니다.",
)
def get_fcm_tokens(
    db: DbSession,
    user_id: CurrentUserId,
):
    """FCM 토큰 목록 조회"""
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    data = notification_service.get_user_tokens(user_id)

    return GetFcmTokensResponse(
        data=data,
        message="FCM 토큰 목록을 성공적으로 조회했습니다.",
    )


@router.delete(
    "/tokens/{token_id}",
    response_model=StringResponse,
    summary="FCM 토큰 삭제",
    description="지정된 FCM 토큰을 삭제(비활성화)합니다.",
)
def delete_fcm_token(
    db: DbSession,
    user_id: CurrentUserId,
    token_id: str,
):
    """FCM 토큰 삭제"""
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    notification_service.delete_token(user_id, token_id)

    data = "deleted"

    return StringResponse(
        message="FCM 토큰이 성공적으로 삭제되었습니다.",
        data=data,
    )


# ==================== 알림 설정 관리 ====================


@router.get(
    "/settings",
    response_model=NotificationSettingsResponse,
    summary="알림 설정 조회",
    description="현재 사용자의 알림 설정을 조회합니다.",
)
def get_notification_settings(
    db: DbSession,
    user_id: CurrentUserId,
):
    """알림 설정 조회"""
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    data = notification_service.get_notification_settings(user_id)

    return NotificationSettingsResponse(
        data=data,
        message="알림 설정을 성공적으로 조회했습니다.",
    )


@router.patch(
    "/settings",
    response_model=NotificationSettingsResponse,
    summary="알림 설정 업데이트",
    description="사용자의 알림 설정을 업데이트합니다.",
)
def update_notification_settings(
    db: DbSession,
    user_id: CurrentUserId,
    settings_data: NotificationSettingsUpdate,
):
    """알림 설정 업데이트"""
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    data = notification_service.update_notification_settings(user_id, settings_data)

    return NotificationSettingsResponse(
        data=data,
        message="알림 설정이 성공적으로 업데이트되었습니다.",
    )


# ==================== 알림 전송 ====================
@router.post(
    "/diary-reminder",
    response_model=SendNotificationResponse,
    summary="[관리자/테스트] 다이어리 작성 알림 수동 전송",
    description="테스트 또는 관리 목적으로 현재 사용자에게 다이어리 작성 알림을 수동 전송합니다. 일반적으로는 개인화된 스케줄러에 의해 자동 발송됩니다.",
)
async def send_diary_reminder_manual(
    db: DbSession,
    user_id: CurrentUserId,
):
    """다이어리 작성 알림 수동 전송 (관리자/테스트용)

    주의: 이 엔드포인트는 테스트나 관리 목적으로만 사용해야 합니다.
    실제 운영에서는 개인화된 스케줄러(diary_reminder_scheduler.py)에 의해
    사용자별 설정 시간에 맞춰 자동으로 알림이 발송됩니다.
    """
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    data = await notification_service.send_diary_reminder(user_id)

    return SendNotificationResponse(
        data=data,
        message="다이어리 작성 알림이 수동으로 전송되었습니다. (테스트/관리용)",
    )


@router.post(
    "/ai-content-ready/{diary_id}",
    response_model=SendNotificationResponse,
    summary="[관리자/테스트] AI 콘텐츠 준비 완료 알림 수동 전송",
    description="테스트 또는 관리 목적으로 현재 사용자의 다이어리에 대한 AI 콘텐츠 생성 완료 알림을 수동 전송합니다. 일반적으로는 다이어리 생성 시 자동으로 발송됩니다.",
)
async def send_ai_content_ready_manual(
    db: DbSession,
    user_id: CurrentUserId,
    diary_id: UUID,
):
    """AI 콘텐츠 준비 완료 알림 수동 전송 (관리자/테스트용)

    주의: 이 엔드포인트는 테스트나 관리 목적으로만 사용해야 합니다.
    실제 운영에서는 다이어리 생성 시(DiaryService.create_diary)에 의해
    자동으로 알림이 발송됩니다.
    """
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    data = await notification_service.send_ai_content_ready(user_id, diary_id)

    return SendNotificationResponse(
        message="AI 콘텐츠 준비 완료 알림이 수동으로 전송되었습니다. (테스트/관리용)",
        data=data,
    )


# ==================== 알림 이력 조회 ====================


@router.get(
    "/history",
    response_model=NotificationHistoryResponse,
    summary="알림 이력 조회",
    description="현재 사용자의 알림 전송 이력을 조회합니다.",
)
def get_notification_history(
    db: DbSession,
    user_id: CurrentUserId,
    limit: int = Query(20, le=100, description="조회할 개수"),
    offset: int = Query(0, ge=0, description="건너뛸 개수"),
):
    """알림 이력 조회"""
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    data = notification_service.get_notification_history(user_id, limit, offset)

    return NotificationHistoryResponse(
        data=data,
        message="알림 이력을 성공적으로 조회했습니다.",
    )


# ==================== 알림 읽음 처리 ====================


@router.patch(
    "/{notification_id}/read",
    response_model=MarkNotificationAsReadResponse,
    summary="알림 읽음 처리",
    description="알림을 읽음으로 표시하고 관련 히스토리도 동시에 업데이트합니다.",
)
async def mark_notification_as_read(
    db: DbSession,
    user_id: CurrentUserId,
    notification_id: UUID,
):
    """알림 읽음 처리 - 양쪽 테이블 동기화"""
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    data = notification_service.mark_notification_as_read(user_id, notification_id)

    return MarkNotificationAsReadResponse(
        message="알림이 읽음으로 처리되었습니다.",
        data=data,
    )


@router.patch(
    "/read-all",
    response_model=MarkNotificationsAsReadResponse,
    summary="모든 알림 읽음 처리",
    description="사용자의 모든 읽지 않은 알림을 읽음으로 표시합니다.",
)
async def mark_all_notifications_as_read(
    db: DbSession,
    user_id: CurrentUserId,
):
    """모든 알림 읽음 처리"""
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    data = notification_service.mark_all_notifications_as_read(user_id)

    return MarkNotificationsAsReadResponse(
        message="모든 알림이 읽음으로 처리되었습니다.",
        data=data,
    )


# ==================== 알림 삭제 ====================


@router.delete(
    "/{notification_id}",
    response_model=DeleteNotificationResponse,
    summary="알림 삭제",
    description="지정된 알림을 삭제합니다 (관련 히스토리도 함께 정리).",
)
async def delete_notification(
    db: DbSession,
    user_id: CurrentUserId,
    notification_id: UUID,
):
    """알림 삭제 처리"""
    fcm_service = get_fcm_service()
    notification_service = NotificationService(db, fcm_service)

    data = notification_service.delete_notification(user_id, notification_id)

    return DeleteNotificationResponse(
        data=data,
        message="알림이 삭제되었습니다.",
    )
