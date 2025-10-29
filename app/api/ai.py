"""
AI 관련 API 라우터
AI 텍스트 생성 및 사용 로그 관리
"""

import asyncio

from fastapi import APIRouter, Path
from fastapi.responses import StreamingResponse

from app.core.deps import (
    AIServiceDep,
    CreateAIUsageLogServiceDep,
    CurrentUser,
    CurrentUserId,
)
from app.schemas.ai import (
    CreateAiUsageLogRequest,
    CreateAiUsageLogResponse,
    GetOriginalUserInputResponse,
)
from app.schemas.create_diary import CreateDiaryRequest
from app.schemas.localization import LanguageCode

router = APIRouter(
    tags=["AI"],
)


# CHECK: 미사용 여부 확인 필요
@router.post(
    "/usage-log",
    response_model=CreateAiUsageLogResponse,
)
async def create_ai_usage_log(
    create_ai_usage_log_service: CreateAIUsageLogServiceDep,
    user_id: CurrentUserId,
    request: CreateAiUsageLogRequest,
):
    """AI 사용 로그 생성"""
    data = await create_ai_usage_log_service.create_ai_usage_log(
        user_id,
        request,
    )

    return CreateAiUsageLogResponse(
        data=data,
        message="AI 사용 로그가 생성되었습니다.",
    )


# CHECK: 미사용 여부 확인 필요
@router.get(
    "/session/{session_id}/original-input",
    response_model=GetOriginalUserInputResponse,
)
async def get_original_user_input(
    ai_service: AIServiceDep,
    user_id: CurrentUserId,
    *,
    session_id: str = Path(..., description="세션 ID"),
):
    """세션ID로 원본 사용자 입력 조회"""
    data = await ai_service.get_original_user_input(user_id, session_id)

    return GetOriginalUserInputResponse(
        data=data,
        message="원본 사용자 입력 조회 성공",
    )


@router.post("/generate/stream")
async def stream_ai_text(
    ai_service: AIServiceDep,
    user_id: CurrentUserId,
    current_user: CurrentUser,
    data: CreateDiaryRequest,
):
    """AI 텍스트 실시간 스트리밍 생성"""

    if data.target_language is not None:
        preferred_language = data.target_language
    else:
        try:
            preferred_language = (
                LanguageCode(current_user.preferred_language)
                if current_user and current_user.preferred_language
                else LanguageCode.KO
            )
        except ValueError:
            preferred_language = LanguageCode.KO

    async def generate_stream():
        try:
            # 즉시 연결 확립 신호 전송 (브라우저 대기 상태 해제)
            keepalive = 'data: {"type": "connected"}\n\n'
            yield keepalive.encode("utf-8")
            await asyncio.sleep(0.01)  # 즉시 플러시

            async for chunk in ai_service.stream_ai_text(
                user_id, data, preferred_language.value
            ):
                chunk_data = f"data: {chunk}\n\n"
                yield chunk_data.encode("utf-8")  # 바이트 기반 전송으로 강제 플러싱
        except Exception as e:
            error_message = (
                f'{{"error": "AI 텍스트 생성 중 오류가 발생했습니다: {str(e)}"}}'
            )
            yield f"data: {error_message}\n\n".encode()
            yield b"event: error\n"
            yield f"data: {error_message}\n\n".encode()

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",  # Nginx 버퍼링 방지
            "Transfer-Encoding": "chunked",  # 청크 기반 전송 명시
            "Pragma": "no-cache",  # HTTP/1.0 호환성
            "Expires": "0",  # 즉시 만료
            "Content-Encoding": "identity",  # 압축 방지
        },
    )


# CHECK: 미사용 여부 확인 필요
@router.post("/regenerate/{session_id}/stream")
async def stream_regenerate_ai_text(
    ai_service: AIServiceDep,
    user_id: CurrentUserId,
    current_user: CurrentUser,
    session_id: str,
):
    """세션 ID 기반 AI 텍스트 실시간 스트리밍 재생성"""

    async def regenerate_stream():
        try:
            # 즉시 연결 확립 신호 전송 (브라우저 대기 상태 해제)
            keepalive = 'data: {"type": "connected"}\n\n'
            yield keepalive.encode("utf-8")
            await asyncio.sleep(0.01)  # 즉시 플러시

            try:
                regenerate_language = (
                    LanguageCode(current_user.preferred_language)
                    if current_user and current_user.preferred_language
                    else LanguageCode.KO
                )
            except ValueError:
                regenerate_language = LanguageCode.KO

            async for chunk in ai_service.stream_regenerate_by_session_id(
                user_id,
                session_id,
                regenerate_language.value,
            ):
                chunk_data = f"data: {chunk}\n\n"
                yield chunk_data.encode("utf-8")  # 바이트 기반 전송으로 강제 플러싱
        except Exception as e:
            error_message = (
                f'{{"error": "AI 텍스트 재생성 중 오류가 발생했습니다: {str(e)}"}}'
            )
            yield f"data: {error_message}\n\n".encode()
            yield b"event: error\n"
            yield f"data: {error_message}\n\n".encode()

    return StreamingResponse(
        regenerate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",  # Nginx 버퍼링 방지
            "Transfer-Encoding": "chunked",  # 청크 기반 전송 명시
            "Pragma": "no-cache",  # HTTP/1.0 호환성
            "Expires": "0",  # 즉시 만료
            "Content-Encoding": "identity",  # 압축 방지
        },
    )
