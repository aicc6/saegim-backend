"""
관리자용 데이터 정리 API
"""

from fastapi import APIRouter

from app.core.deps import DbSession
from app.schemas.cleanup import (
    CleanupExpiredSoftDeletedDataResponse,
    GetSoftDeletedStatisticsResponse,
)
from app.services.cleanup_service import CleanupService

router = APIRouter(tags=["Admin"])


@router.post(
    "/cleanup/expired-data",
    response_model=CleanupExpiredSoftDeletedDataResponse,
)
async def cleanup_expired_data(
    db: DbSession,
):
    """
    30일 경과된 Soft Delete 데이터 영구 삭제 (관리자용)

    Args:
        db: 데이터베이스 세션

    Returns:
        삭제 결과 통계
    """
    cleanup_service = CleanupService(db)

    data = cleanup_service.cleanup_expired_soft_deleted_data()

    return CleanupExpiredSoftDeletedDataResponse(
        data=data,
        message="영구 삭제가 완료되었습니다.",
    )


@router.get(
    "/cleanup/statistics",
    response_model=GetSoftDeletedStatisticsResponse,
)
async def get_cleanup_statistics(
    db: DbSession,
):
    """
    Soft Delete 데이터 통계 조회 (관리자용)

    Args:
        db: 데이터베이스 세션

    Returns:
        Soft Delete 데이터 통계
    """
    cleanup_service = CleanupService(db)

    statistics = cleanup_service.get_soft_deleted_statistics()

    return GetSoftDeletedStatisticsResponse(
        data=statistics,
        message="통계 조회가 완료되었습니다.",
    )
