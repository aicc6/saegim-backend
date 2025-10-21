"""
다이어리 API 라우터 (JWT 인증 기반)
"""

import logging
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    File,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)

from app.constants import SortOrder
from app.core.deps import AIServiceDep, CurrentUserId, DiaryServiceDep
from app.schemas.base import BaseResponse, MessageResponse, MessageResponseData
from app.schemas.diary import (
    DiaryContentResponse,
    DiaryContentResponseData,
    DiaryCreateRequest,
    DiaryListResponse,
    DiaryListResponseData,
    DiaryResponse,
    DiaryResponseData,
    DiaryUpdateRequest,
    GetDiaryImageResponse,
    HandwritingToDiaryRequest,
    UploadHandWritingImageResponse,
    UploadHandWritingImageResponseData,
    UploadHandWritingImagesResponse,
    UploadImageResponse,
)
from app.utils.minio_upload import (
    upload_image_with_thumbnail_to_minio,
)
from app.utils.openai_utils import handwriting_ocr_from_url
from app.utils.validators import (
    validate_image_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Diary"])


@router.post("/handwriting/to-diary", response_model=BaseResponse[dict])
async def handwriting_to_diary(
    ai_service: AIServiceDep,
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    body: HandwritingToDiaryRequest = Body(...),
):
    """
    손글씨 이미지 URL 전달 시, OCR(텍스트추출)+AI 다이어리 자동생성까지 모두 처리
    """
    logger.info(
        f"손글씨 OCR 시작 - user_id: {user_id}, image_url: {body.image_url}, user_emotion: {body.user_emotion}"
    )

    # 사용자 감정 검증 로그
    if body.user_emotion:
        logger.info(f"사용자 선택 감정: {body.user_emotion}")
    else:
        logger.info("사용자 감정 미선택")

    # OCR - 손글씨 텍스트 추출
    ocr_text = await handwriting_ocr_from_url(body.image_url)
    logger.info(f"OCR 결과: {ocr_text[:100]}..." if ocr_text else "OCR 결과 없음")

    if not ocr_text or len(ocr_text.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="손글씨 이미지에서 글씨를 인식하지 못했습니다. 이미지를 다시 확인해 주세요.",
        )

    # AI 텍스트 생성 (비동기)
    logger.info("AI 다이어리 텍스트 생성 시작")
    generated_text = ""
    async for text_chunk in ai_service._stream_complete_analysis(
        ocr_text, body.style, body.length
    ):
        if isinstance(text_chunk, dict) and "tokens_used" in text_chunk:
            continue
        generated_text += text_chunk

    # AI 생성된 텍스트 정리
    ai_generated_text = generated_text.strip()
    logger.info(f"AI 다이어리 텍스트 생성 완료: {ai_generated_text[:100]}...")

    # 감정 분석 및 키워드 추출
    try:
        analysis_result = await ai_service._integrated_analysis(
            ocr_text, body.style, body.length
        )
        ai_emotion = analysis_result["emotion"]
        keywords = analysis_result["keywords"]
        logger.info(f"감정 분석 완료: emotion='{ai_emotion}', keywords={keywords}")
    except Exception as e:
        logger.warning(f"감정 분석 실패: {str(e)}")
        ai_emotion = None
        keywords = None

    # save 파라미터에 따른 처리 분기
    if body.save:
        # 다이어리 실제 저장
        request = DiaryCreateRequest(
            title=None,  # AI가 자동 생성
            content=ai_generated_text,  # AI가 생성한 다이어리 텍스트
            user_emotion=body.user_emotion,  # 사용자가 선택한 감정
            ai_generated_text=ai_generated_text,  # AI가 생성한 텍스트
            ocr_text=ocr_text,  # OCR 원본 텍스트
            ai_emotion=ai_emotion,  # AI가 분석한 감정
            ai_emotion_confidence=None,
            keywords=keywords,
            diary_date=None,
            uploaded_images=(
                body.uploaded_images
                if body.uploaded_images
                else [
                    {
                        "original_url": body.image_url,
                        "thumbnail_url": None,
                        "mime_type": None,
                        "file_size": None,
                    }
                ]
            ),
        )

        logger.info(
            f"다이어리 저장 시작 - user_emotion: {body.user_emotion}, ai_emotion: {ai_emotion}"
        )
        created_diary = diary_service.create_diary(user_id, request)
        logger.info(f"다이어리 저장 완료 - diary_id: {created_diary.id}")

        return BaseResponse(
            data=DiaryResponseData.model_validate(created_diary).model_dump(),
            message="손글씨 인식 후 다이어리 생성 완료",
        )
    else:
        # 미리보기 데이터만 반환 (저장하지 않음)
        preview_data = {
            "ocr_text": ocr_text,
            "ai_generated_text": ai_generated_text,
            "ai_emotion": ai_emotion,
            "keywords": keywords,
            "user_emotion": body.user_emotion,
            "style": body.style,
            "length": body.length,
            "image_url": body.image_url,
            "uploaded_images": (
                body.uploaded_images
                if body.uploaded_images
                else [
                    {
                        "original_url": body.image_url,
                        "thumbnail_url": None,
                        "mime_type": None,
                        "file_size": None,
                    }
                ]
            ),
        }

        logger.info("다이어리 미리보기 데이터 생성 완료 (저장하지 않음)")
    return BaseResponse(
        data=preview_data,
        message="손글씨 인식 및 AI 다이어리 미리보기 생성 완료",
    )


@router.get("", response_model=DiaryListResponse)
async def get_my_diaries(
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    page: Annotated[int, Query(ge=1, description="페이지 번호")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="페이지 크기")] = 20,
    searchTerm: Annotated[str | None, Query(description="제목/내용 통합 검색")] = None,
    emotion: Annotated[str | None, Query(description="감정 필터")] = None,
    start_date: Annotated[
        date | None, Query(description="시작 날짜 (YYYY-MM-DD)")
    ] = None,
    end_date: Annotated[
        date | None, Query(description="종료 날짜 (YYYY-MM-DD)")
    ] = None,
    sort_order: str = Query(
        SortOrder.DESC.value,
        description="정렬 순서 (asc: 오름차순, desc: 내림차순)",
        regex="^(asc|desc)$",
    ),
):
    """JWT 인증된 사용자의 다이어리 목록 조회 (페이지네이션 포함)"""

    data, total_count = diary_service.get_diaries(
        user_id=user_id,  # JWT에서 추출한 사용자 ID 사용
        page=page,
        page_size=page_size,
        searchTerm=searchTerm,
        emotion=emotion,
        start_date=start_date,
        end_date=end_date,
        sort_order=sort_order,
    )

    return DiaryListResponse(
        data=[DiaryListResponseData.model_validate(diary) for diary in data],
        message=f"다이어리 목록 조회 성공 (총 {total_count}개)",
    )


@router.get(
    "/calendar",
    response_model=DiaryListResponse,
)
async def get_calendar_diaries(
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    start_date: Annotated[date, Query(description="시작 날짜 (YYYY-MM-DD)")],
    end_date: Annotated[date, Query(description="종료 날짜 (YYYY-MM-DD)")],
):
    """JWT 인증된 사용자의 캘린더용 다이어리 조회 (특정 날짜 범위)"""

    data = diary_service.get_diaries_by_date_range(
        user_id=user_id,  # JWT에서 추출한 사용자 ID 사용
        start_date=start_date,
        end_date=end_date,
    )

    return DiaryListResponse(
        data=[DiaryListResponseData.model_validate(diary) for diary in data],
        message=f"캘린더 다이어리 조회 성공 (총 {len(data)}개)",
    )


@router.get(
    "/{diary_id}/content",
    response_model=DiaryContentResponse,
)
async def get_diary_content(
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    diary_id: UUID = Path(..., description="다이어리 ID (UUID)"),
):
    """JWT 인증된 사용자의 특정 다이어리 content만 조회"""

    diary = diary_service.get_diary(user_id, diary_id)

    return DiaryContentResponse(
        data=DiaryContentResponseData(id=str(diary.id), content=diary.content),
        message="다이어리 content 조회 성공",
    )


@router.get(
    "/{diary_id}",
    response_model=DiaryResponse,
)
async def get_diary(
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    diary_id: UUID = Path(..., description="다이어리 ID (UUID)"),
):
    """JWT 인증된 사용자의 특정 다이어리 조회"""

    data = diary_service.get_diary(user_id, diary_id)

    return DiaryResponse(
        data=DiaryResponseData.model_validate(data),
        message="다이어리 조회 성공",
    )


@router.post(
    "/{diary_id}/upload-image",
    response_model=UploadImageResponse,
)
async def upload_diary_image(
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    diary_id: UUID = Path(..., description="다이어리 ID (UUID)"),
    image: Annotated[UploadFile, File(description="업로드할 이미지 파일")],
):
    """다이어리에 이미지 업로드"""

    data = await diary_service.upload_diary_image(user_id, diary_id, image)

    return UploadImageResponse(
        data=data,
        message="이미지 업로드 성공",
    )


@router.delete(
    "/{diary_id}/images/{image_id}",
    response_model=MessageResponse,
)
async def delete_diary_image(
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    diary_id: UUID = Path(..., description="다이어리 ID (UUID)"),
    image_id: UUID = Path(..., description="이미지 ID (UUID)"),
):
    """다이어리 이미지 삭제"""
    diary_service.delete_diary_image(user_id, diary_id, image_id)

    data = MessageResponseData(message="이미지 삭제 성공")

    return MessageResponse(
        data=data,
        message="이미지가 성공적으로 삭제되었습니다.",
    )


@router.get(
    "/{diary_id}/images",
    response_model=GetDiaryImageResponse,
)
async def get_diary_images(
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    diary_id: UUID = Path(..., description="다이어리 ID (UUID)"),
):
    """다이어리의 기존 이미지들 조회"""

    data = diary_service.get_diary_images(user_id, diary_id)

    return GetDiaryImageResponse(
        data=data,
        message=f"다이어리 이미지 조회 성공 (총 {len(data)}개)",
    )


@router.post(
    "/images/upload",
    response_model=UploadHandWritingImagesResponse,
)
async def upload_temporary_images(
    user_id: CurrentUserId,
    *,
    images: Annotated[
        list[UploadFile], File(description="업로드할 이미지 파일들", max_length=10)
    ],
):
    """AI 글 생성용 임시 이미지 업로드 (다이어리 저장 시 연결됨)"""

    data: list[UploadHandWritingImageResponseData] = []

    for image in images:
        # 이미지 파일 검증
        validate_image_file(image.content_type, image.size or 0)

        # MinIO에 이미지 업로드 (썸네일 포함)
        (
            file_id,
            original_url,
            thumbnail_url,
        ) = await upload_image_with_thumbnail_to_minio(image)

        # 업로드된 이미지 정보 저장
        image_info = UploadHandWritingImageResponseData(
            file_id=file_id,
            original_url=original_url,
            thumbnail_url=thumbnail_url,
            mime_type=image.content_type,
            file_size=image.size,
            filename=image.filename,
        )
        data.append(image_info)

    return UploadHandWritingImagesResponse(
        data=data,
        message=f"이미지 업로드 성공 (총 {len(data)}개)",
    )


@router.post(
    "/handwriting/upload",
    response_model=UploadHandWritingImageResponse,
)
async def upload_handwriting_image(
    user_id: CurrentUserId,
    *,
    image: Annotated[UploadFile, File(description="손글씨 이미지 파일")],
):
    """
    손글씨 텍스트 인식용 임시 이미지 업로드 (AI 다이어리 자동생성 본문으로 활용)
    """
    validate_image_file(image.content_type, image.size or 0)

    (
        file_id,
        original_url,
        thumbnail_url,
    ) = await upload_image_with_thumbnail_to_minio(image)

    data = UploadHandWritingImageResponseData(
        file_id=file_id,
        original_url=original_url,
        thumbnail_url=thumbnail_url,
        mime_type=image.content_type,
        file_size=image.size,
        filename=image.filename,
    )

    return UploadHandWritingImageResponse(
        data=data,
        message="손글씨 이미지 업로드 성공 (다음: 텍스트 추출 단계)",
    )


@router.post(
    "",
    response_model=DiaryResponse,
)
async def create_diary(
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    request: DiaryCreateRequest,
):
    """JWT 인증된 사용자의 다이어리 생성"""

    # diary_id 변수 제거하고 diary_create와 user_id만 전달
    data = diary_service.create_diary(user_id, request)

    return DiaryResponse(
        data=DiaryResponseData.model_validate(data),
        message="다이어리 생성 성공",
    )


@router.put(
    "/{diary_id}",
    response_model=DiaryResponse,
)
async def update_diary(
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    diary_id: UUID = Path(..., description="다이어리 ID (UUID)"),
    request: DiaryUpdateRequest,
):
    """JWT 인증된 사용자의 다이어리 수정"""

    data = diary_service.update_diary(user_id, diary_id, request)

    return DiaryResponse(
        data=DiaryResponseData.model_validate(data),
        message="다이어리 수정 성공",
    )


@router.delete(
    "/{diary_id}",
    response_model=MessageResponse,
)
async def delete_diary(
    diary_service: DiaryServiceDep,
    user_id: CurrentUserId,
    *,
    diary_id: UUID,
):
    """JWT 인증된 사용자의 다이어리 삭제 (Soft Delete)"""

    # 다이어리 삭제 시도
    diary_service.delete_diary(user_id=user_id, diary_id=diary_id)

    return MessageResponse(
        data=MessageResponseData(message="다이어리 삭제 성공"),
        message="다이어리가 성공적으로 삭제되었습니다.",
    )
