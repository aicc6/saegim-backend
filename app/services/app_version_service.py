import logging
from datetime import timedelta

from sqlalchemy import desc, exists, select
from sqlalchemy.orm import Session

from app.core.transaction_manager import TransactionManager
from app.exceptions.app_version import (
    AppVersionAlreadyExistsException,
    LatestVersionNotFoundException,
)
from app.models.app_version import AppVersion
from app.schemas.app_version import (
    CheckAppVersionRequest,
    CheckAppVersionResponseData,
    UploadAppRequest,
    UploadAppResponseData,
)
from app.services.base import BaseService
from app.services.minio_service import MinioService

logger = logging.getLogger(__name__)


class AppVersionService(BaseService):
    def __init__(self, db: Session, minio_service: MinioService):
        super().__init__(db)

        self._minio_service = minio_service

    async def upload_app(self, request: UploadAppRequest):
        file_extension = (
            request.file.filename.split(".")[-1].lower()
            if request.file.filename
            else ""
        )
        allowed_extensions = {
            "ios": ["ipa"],
            "android": ["apk", "aab"],
        }

        platform_value = request.platform.value

        if file_extension not in allowed_extensions.get(platform_value, []):
            raise ValueError(
                f"{platform_value} 플랫폼은 {', '.join(allowed_extensions[platform_value])} 파일만 허용됩니다.",
            )
        # 동일한 버전이 이미 존재하는지 확인
        with TransactionManager.transaction(self._db) as tx:
            self.__check_existing_version(
                platform_value,
                request.version_name,
                tx,
            )

            # MinIO에 파일 업로드
            object_name = f"app-versions/{platform_value}/{request.version_name}/{request.file.filename}"

            file_path, file_size = await self._minio_service.upload_file(
                file=request.file,
                object_name=object_name,
                content_type=request.file.content_type,
            )

            # 데이터베이스에 버전 정보 저장
            app_version = AppVersion(
                version_name=request.version_name,
                platform=platform_value,
                description=request.description,
                file_path=file_path,
                file_size=file_size,
                file_name=request.file.filename or "unknown",
                is_mandatory=request.is_mandatory,
                is_active=True,
            )

            tx.add(app_version)

        # 다운로드 URL 생성
        download_url = await self._minio_service.get_presigned_url(
            object_name=file_path,
            expires=timedelta(hours=1),
        )

        response = UploadAppResponseData.model_validate(app_version)
        response.download_url = download_url

        logger.info(f"앱 버전 업로드 성공: {request.platform} {request.version_name}")

        return response

    async def check_app_version(self, request: CheckAppVersionRequest):
        # 최신 활성 버전 조회
        latest_version = self._db.execute(
            select(AppVersion)
            .where(
                AppVersion.platform == request.platform,
                AppVersion.is_active == True,  # noqa: E712
            )
            .order_by(desc(AppVersion.created_at))
        ).scalar_one_or_none()

        # 최신 버전이 없거나 현재 버전과 같으면 업데이트 불필요
        if not latest_version or latest_version.version_name == request.current_version:
            return CheckAppVersionResponseData(
                has_update=False,
                is_mandatory=False,
                latest_version=None,
                message="현재 최신 버전을 사용 중입니다.",
            )

        # 다운로드 URL 생성
        download_url = await self._minio_service.get_presigned_url(
            object_name=latest_version.file_path,
            expires=timedelta(hours=1),
        )

        response_version = UploadAppResponseData.model_validate(latest_version)
        response_version.download_url = download_url

        message = f"새로운 버전 {latest_version.version_name}이(가) 출시되었습니다."
        if latest_version.is_mandatory:
            message += " (필수 업데이트)"

        return CheckAppVersionResponseData(
            has_update=True,
            is_mandatory=latest_version.is_mandatory,
            latest_version=response_version,
            message=message,
        )

    async def get_latest_version(self, platform: str):
        latest_version = self._db.execute(
            select(AppVersion)
            .where(
                AppVersion.platform == platform,
                AppVersion.is_active == True,  # noqa: E712
            )
            .order_by(desc(AppVersion.created_at))
        ).scalar_one_or_none()
        if not latest_version:
            raise LatestVersionNotFoundException(
                platform=platform,
            )

        # 다운로드 URL 생성
        download_url = await self._minio_service.get_presigned_url(
            object_name=latest_version.file_path,
            expires=timedelta(hours=1),
        )

        response = UploadAppResponseData.model_validate(latest_version)
        response.download_url = download_url

        return response

    def __check_existing_version(
        self,
        platform: str,
        version_name: str,
        tx: Session,
    ):
        stmt = select(
            exists().where(
                AppVersion.version_name == version_name,
                AppVersion.platform == platform,
            )
        )
        existing_version = tx.execute(stmt).scalar_one()

        if existing_version:
            raise AppVersionAlreadyExistsException(
                platform=platform,
                version_name=version_name,
            )
