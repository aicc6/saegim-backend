"""다이어리 카테고리 API"""

import logging
from fastapi import APIRouter, Body, Path, status

from app.core.deps import CurrentUserId, DiaryCategoryServiceDep
from app.schemas.base import MessageResponse, MessageResponseData
from app.schemas.category import (
    DiaryCategoryCreateRequest,
    DiaryCategoryListResponse,
    DiaryCategoryResponse,
    DiaryCategoryResponseData,
    DiaryCategoryUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Diary Category"])


@router.get("", response_model=DiaryCategoryListResponse)
async def list_categories(
    category_service: DiaryCategoryServiceDep,
    user_id: CurrentUserId,
):
    """현재 사용자 카테고리 목록 조회"""
    categories = category_service.list_categories(user_id)
    data = [DiaryCategoryResponseData.model_validate(category) for category in categories]
    logger.debug("Returning %d categories for user %s", len(data), user_id)
    return DiaryCategoryListResponse(
        data=data,
        message="카테고리 목록 조회 성공",
    )


@router.post(
    "",
    response_model=DiaryCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    category_service: DiaryCategoryServiceDep,
    user_id: CurrentUserId,
    *,
    request: DiaryCategoryCreateRequest = Body(...),
):
    """새 카테고리 생성"""
    category = category_service.create_category(user_id, request)
    return DiaryCategoryResponse(
        data=DiaryCategoryResponseData.model_validate(category),
        message="카테고리 생성 성공",
    )


@router.patch(
    "/{category_id}",
    response_model=DiaryCategoryResponse,
)
async def update_category(
    category_service: DiaryCategoryServiceDep,
    user_id: CurrentUserId,
    *,
    category_id: str = Path(..., description="카테고리 ID"),
    request: DiaryCategoryUpdateRequest = Body(...),
):
    """카테고리 수정"""
    category = category_service.update_category(user_id, category_id, request)
    return DiaryCategoryResponse(
        data=DiaryCategoryResponseData.model_validate(category),
        message="카테고리 수정 성공",
    )


@router.delete(
    "/{category_id}",
    response_model=MessageResponse,
)
async def delete_category(
    category_service: DiaryCategoryServiceDep,
    user_id: CurrentUserId,
    *,
    category_id: str = Path(..., description="카테고리 ID"),
):
    """카테고리 삭제"""
    category_service.delete_category(user_id, category_id)
    return MessageResponse(
        data=MessageResponseData(message="카테고리 삭제 성공"),
        message="카테고리가 성공적으로 삭제되었습니다.",
    )
