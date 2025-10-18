"""
회원가입 및 이메일 인증 API 라우터
이메일 회원가입, 이메일 인증, 중복 확인
"""

import logging

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.deps import AuthServiceDep
from app.schemas.auth import (
    EmailVerificationConfirmRequest,
    EmailVerificationRequest,
    SignUpResponse,
    SignupRequest,
)
from app.schemas.base import BaseResponse, MessageResponse

router = APIRouter(tags=["Registration"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/signup", response_model=SignUpResponse)
async def signup(
    auth_service: AuthServiceDep,
    request: SignupRequest,
):
    """이메일 회원가입 API"""
    data = await auth_service.sign_up(request)

    return SignUpResponse(
        data=data,
        message="회원가입이 성공적으로 완료되었습니다.",
    )


@router.get("/check-email/{email}")
async def check_email_availability(
    auth_service: AuthServiceDep,
    email: str,
):
    """이메일 중복 확인 API"""
    data = auth_service.check_email_availability(email)

    return BaseResponse(
        data=data,
        message="이메일 중복 확인이 완료되었습니다.",
    )


@router.get("/check-nickname/{nickname}")
async def check_nickname_availability(
    auth_service: AuthServiceDep,
    nickname: str,
):
    """닉네임 중복 확인 API"""
    data = auth_service.check_nickname_availability(nickname)

    return BaseResponse(
        data=data,
        message="닉네임 중복 확인이 완료되었습니다.",
    )


@router.post("/send-verification-email", response_model=MessageResponse)
async def send_verification_email(
    auth_service: AuthServiceDep,
    request: EmailVerificationRequest,
):
    """이메일 인증 코드 발송 API"""
    logger.info(f"인증 코드 발송 요청 시작: {request.email}")
    data = await auth_service.send_verification_email(request)

    return MessageResponse(
        data=data,
        message="인증 코드가 이메일로 발송되었습니다.",
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    auth_service: AuthServiceDep,
    request: EmailVerificationConfirmRequest,
):
    """이메일 인증 코드 확인 API"""
    data = auth_service.verify_email(request)

    return MessageResponse(
        data=data,
        message="이메일 인증이 성공적으로 완료되었습니다.",
    )
