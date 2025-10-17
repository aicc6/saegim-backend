"""
고객센터 문의 API 라우터
로그인한 사용자만 문의 접수 및 관리자 이메일 발송
"""

import logging

from fastapi import APIRouter

from app.core.deps import CurrentUser
from app.schemas.support import (
    CreateInquiryRequest,
    CreateInquiryResponse,
)
from app.services.support_service import SupportService
from app.utils.email_service import EmailService

router = APIRouter(tags=["Support"])
logger = logging.getLogger(__name__)


# 문의 요청 모델
@router.post(
    "/inquiries",
    response_model=CreateInquiryResponse,
)
async def create_inquiry(
    current_user: CurrentUser,
    request: CreateInquiryRequest,
):
    """
    고객센터 문의 접수 (로그인한 사용자만)

    Args:
        request: 문의 내용
        current_user: 현재 로그인한 사용자

    Returns:
        문의 접수 결과
    """
    email_service = EmailService()
    support_service = SupportService(email_service)

    data = await support_service.create_inquiry(current_user, request)

    return CreateInquiryResponse(
        data=data,
        message="문의가 성공적으로 접수되었습니다.",
    )

    # except Exception as e:
    #     logger.error(f"Support inquiry creation failed: {e}")
    #     raise HTTPException(
    #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #         detail="문의 접수 중 오류가 발생했습니다.",
    #     ) from e
