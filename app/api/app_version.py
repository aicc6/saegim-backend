"""
앱 버전 관리 API
"""

import logging
from typing import Any

from fastapi import (
    APIRouter,
    File,
    Form,
    Query,
    UploadFile,
    status,
)

from app.core.deps import AppVersionServiceDep
from app.schemas.app_version import (
    CheckAppVersionRequest,
    CheckAppVersionResponse,
    PlatformType,
    UploadAppRequest,
    UploadAppResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AppVersion"])


@router.post(
    "/upload",
    response_model=UploadAppResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_app(
    app_version_service: AppVersionServiceDep,
    version_name: str = Form(..., description="버전명 (예: 1.0.0)"),
    platform: PlatformType = Form(..., description="플랫폼 (ios, android)"),
    file: UploadFile = File(..., description="앱 파일 (apk, ipa)"),
    description: str | None = Form(None, description="버전 설명"),
    is_mandatory: bool = Form(False, description="필수 업데이트 여부"),
):
    """
    앱 버전 업로드

    개발자가 로컬에서 백엔드 API에 호출하여 앱 파일을 업로드하고 버전 정보를 등록합니다.
    """
    response = await app_version_service.upload_app(
        UploadAppRequest(
            version_name=version_name,
            platform=platform,
            file=file,
            description=description,
            is_mandatory=is_mandatory,
        )
    )

    return UploadAppResponse(
        data=response,
        message="앱 버전이 성공적으로 업로드되었습니다.",
    )


@router.post("/check", response_model=CheckAppVersionResponse)
async def check_app_version(
    app_version_service: AppVersionServiceDep,
    request: CheckAppVersionRequest,
) -> Any:
    """
    앱 업데이트 확인

    앱 실행 시 스플래시 페이지에서 업데이트 가능한 버전이 있는지 확인합니다.
    """
    data = await app_version_service.check_app_version(request)

    return CheckAppVersionResponse(
        data=data,
        message="앱 버전 확인이 완료되었습니다.",
    )


@router.get("/latest", response_model=UploadAppResponse)
async def get_latest_version(
    app_version_service: AppVersionServiceDep,
    platform: PlatformType = Query(..., description="플랫폼 (ios, android)"),
):
    """
    특정 플랫폼의 최신 버전 조회
    """
    response = await app_version_service.get_latest_version(platform)

    return UploadAppResponse(
        data=response,
        message="최신 버전을 조회했습니다.",
    )
