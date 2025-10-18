"""
관리자용 데이터 정리 API
"""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import DbSession
from app.schemas.base import BaseResponse
from app.services.cleanup_service import CleanupService

router = APIRouter(tags=["Admin"])


@router.post("/cleanup/expired-data", response_model=BaseResponse[dict])
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
    try:
        cleanup_service = CleanupService(db)
        result = cleanup_service.cleanup_expired_soft_deleted_data()

        return BaseResponse(
            success=True, data=result, message="영구 삭제가 완료되었습니다."
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"영구 삭제 중 오류가 발생했습니다: {str(e)}",
        ) from e


@router.get("/cleanup/statistics", response_model=BaseResponse[dict])
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
    try:
        cleanup_service = CleanupService(db)
        statistics = cleanup_service.get_soft_deleted_statistics()

        return BaseResponse(
            success=True, data=statistics, message="통계 조회가 완료되었습니다."
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"통계 조회 중 오류가 발생했습니다: {str(e)}",
        ) from e
