"""
MinIO 이미지 업로드 유틸리티 함수
"""

import io
import uuid
import logging
from datetime import datetime
from pathlib import Path

from minio import Minio
from minio.error import S3Error
from fastapi import HTTPException, UploadFile, status
from PIL import Image

from app.core.config import get_settings
from app.constants import FileConstants

# 로깅 설정
logger = logging.getLogger(__name__)


class MinIOUploader:
    """MinIO 이미지 업로드 유틸리티"""

    def __init__(self):
        """MinIO 클라이언트 초기화"""
        try:
            # 설정을 동적으로 가져옴 (테스트 시 환경변수 변경 반영)
            settings = get_settings()

            self.client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            self.bucket_name = settings.minio_bucket_name

            # 버킷 생성 (존재하지 않을 경우)
            self._ensure_bucket_exists()

            logger.info(
                f"MinIO 클라이언트 초기화 성공: {settings.minio_endpoint}, 버킷: {self.bucket_name}"
            )

        except Exception as e:
            logger.error(f"MinIO 클라이언트 초기화 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="MinIO 스토리지 서비스 초기화에 실패했습니다.",
            )

    def _ensure_bucket_exists(self) -> None:
        """버킷 존재 확인 및 생성"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"MinIO 버킷 생성: {self.bucket_name}")

        except S3Error as e:
            logger.error(f"MinIO 버킷 설정 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="MinIO 버킷 설정에 실패했습니다.",
            )

    async def upload_image(self, file: UploadFile):
        """
        이미지를 MinIO에 업로드 (EXIF 제거 포함)

        Args:
            file: 업로드할 파일 객체

        Returns:
            tuple[str, str]: (파일 ID, 이미지 URL)
        """
        try:
            # 파일 검증
            self._validate_file(file)

            # 파일 읽기
            file_content = await file.read()

            # EXIF 데이터 제거
            file_content_without_exif = self._remove_exif(file_content)

            # 고유 파일 ID 생성
            file_id = uuid.uuid4()

            # 객체 키 생성 (폴더 구조: images/YYYY/MM/DD/파일ID.확장자)
            object_key = self._generate_object_key(file_id, file.filename or "unknown")

            # MinIO에 업로드 (EXIF가 제거된 이미지)
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_key,
                data=io.BytesIO(file_content_without_exif),
                length=len(file_content_without_exif),
                content_type=file.content_type,
            )

            # 이미지 URL 생성
            image_url = self._generate_image_url(object_key)

            logger.info(
                f"이미지 업로드 성공 (EXIF 제거됨): {file.filename} -> {object_key}"
            )
            return file_id, image_url

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"이미지 업로드 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"이미지 업로드 중 오류가 발생했습니다: {str(e)}",
            )

    def delete_image(self, object_key: str) -> bool:
        """
        MinIO에서 이미지 삭제

        Args:
            object_key: 삭제할 객체의 키

        Returns:
            bool: 삭제 성공 여부
        """
        try:
            self.client.remove_object(self.bucket_name, object_key)
            logger.info(f"이미지 삭제 성공: {object_key}")
            return True

        except Exception as e:
            logger.error(f"이미지 삭제 실패: {e}")
            return False

    def get_image_url(self, object_key: str) -> str:
        """
        이미지 URL 생성

        Args:
            object_key: 객체 키

        Returns:
            str: 이미지 접근 URL
        """
        return self._generate_image_url(object_key)

    def _remove_exif(self, image_data: bytes) -> bytes:
        """
        이미지에서 EXIF 데이터 제거

        Args:
            image_data: 원본 이미지 데이터

        Returns:
            bytes: EXIF가 제거된 이미지 데이터
        """
        try:
            with Image.open(io.BytesIO(image_data)) as img:
                # EXIF 데이터를 제거하고 새로운 이미지 생성
                # getdata()를 사용하여 픽셀 데이터만 복사
                img_without_exif = Image.new(img.mode, img.size)
                img_without_exif.putdata(list(img.getdata()))

                # 이미지를 BytesIO에 저장
                output = io.BytesIO()

                # 원본 포맷 유지
                img_format = img.format or "JPEG"

                # EXIF 없이 저장 (exif 파라미터를 명시적으로 제외)
                if img_format.upper() == "JPEG":
                    img_without_exif.save(
                        output, format=img_format, quality=95, optimize=True
                    )
                elif img_format.upper() == "PNG":
                    img_without_exif.save(output, format=img_format, optimize=True)
                else:
                    img_without_exif.save(output, format=img_format)

                output.seek(0)
                return output.getvalue()

        except Exception as e:
            logger.error(f"EXIF 제거 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"이미지 처리 중 오류가 발생했습니다: {str(e)}",
            )

    def _create_thumbnail(
        self,
        image_data: bytes,
        size: tuple[int, int] = FileConstants.THUMBNAIL_SIZE,
        quality: int = FileConstants.THUMBNAIL_QUALITY,
    ) -> bytes:
        """
        이미지 데이터로부터 썸네일 생성 (EXIF 제거 포함)

        Args:
            image_data: 원본 이미지 데이터
            size: 썸네일 크기 (기본값: 150x150)
            quality: JPEG 품질 (기본값: 85)

        Returns:
            bytes: EXIF가 제거된 썸네일 이미지 데이터
        """
        try:
            # 이미지 열기
            with Image.open(io.BytesIO(image_data)) as img:
                # RGB 모드로 변환 (RGBA 등 다른 모드 지원)
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")

                # 원본 비율 유지하면서 리사이즈
                img.thumbnail(size, Image.Resampling.LANCZOS)

                # 썸네일 데이터를 BytesIO로 저장 (EXIF 제거)
                thumbnail_buffer = io.BytesIO()
                img.save(
                    thumbnail_buffer,
                    FileConstants.THUMBNAIL_FORMAT,
                    quality=quality,
                    optimize=True,
                    # EXIF 데이터를 명시적으로 제외
                )
                thumbnail_buffer.seek(0)

                return thumbnail_buffer.getvalue()

        except Exception as e:
            logger.error(f"썸네일 생성 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"썸네일 생성 중 오류가 발생했습니다: {str(e)}",
            )

    async def upload_image_with_thumbnail(
        self,
        file: UploadFile,
        thumbnail_size: tuple[int, int] = FileConstants.THUMBNAIL_SIZE,
    ):
        """
        이미지를 MinIO에 업로드하고 썸네일도 생성하여 업로드 (EXIF 제거 포함)

        Args:
            file: 업로드할 파일 객체
            thumbnail_size: 썸네일 크기 (기본값: 150x150)

        Returns:
            tuple[str, str, str]: (파일 ID, 원본 이미지 URL, 썸네일 URL)
        """
        try:
            # 파일 검증
            self._validate_file(file)

            # 파일 읽기
            file_content = await file.read()

            # EXIF 데이터 제거
            file_content_without_exif = self._remove_exif(file_content)

            # 고유 파일 ID 생성
            file_id = uuid.uuid4()

            # 객체 키 생성
            original_object_key = self._generate_object_key(file_id, file.filename)
            thumbnail_object_key = self._generate_thumbnail_object_key(
                file_id, file.filename
            )

            # 원본 이미지 업로드 (EXIF가 제거된 이미지)
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=original_object_key,
                data=io.BytesIO(file_content_without_exif),
                length=len(file_content_without_exif),
                content_type=file.content_type,
            )

            # 썸네일 생성 및 업로드 (이미 EXIF가 제거된 데이터 사용)
            thumbnail_data = self._create_thumbnail(
                file_content_without_exif, thumbnail_size
            )
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=thumbnail_object_key,
                data=io.BytesIO(thumbnail_data),
                length=len(thumbnail_data),
                content_type=f"image/{FileConstants.THUMBNAIL_FORMAT.lower()}",
            )

            # URL 생성
            original_url = self._generate_image_url(original_object_key)
            thumbnail_url = self._generate_image_url(thumbnail_object_key)

            logger.info(
                f"이미지 및 썸네일 업로드 성공 (EXIF 제거됨): {file.filename} -> {original_object_key}, {thumbnail_object_key}"
            )
            return file_id, original_url, thumbnail_url

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"이미지 및 썸네일 업로드 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"이미지 및 썸네일 업로드 중 오류가 발생했습니다: {str(e)}",
            )

    def _validate_file(self, file: UploadFile) -> None:
        """파일 검증"""
        # 파일 크기 확인 (상수 사용)
        if file.size and file.size > FileConstants.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"파일 크기가 {FileConstants.MAX_FILE_SIZE_MB}MB를 초과합니다.",
            )

        # MIME 타입 확인 (상수 사용)
        if file.content_type not in FileConstants.ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"허용되지 않는 파일 형식입니다. 허용된 형식: {', '.join(FileConstants.ALLOWED_IMAGE_TYPES)}",
            )

    def _generate_object_key(self, file_id: uuid.UUID, original_filename: str) -> str:
        """객체 키 생성"""
        file_extension = Path(original_filename).suffix.lower()
        timestamp = datetime.now().strftime("%Y/%m/%d")
        return f"images/{timestamp}/{file_id}{file_extension}"

    def _generate_thumbnail_object_key(
        self, file_id: uuid.UUID, original_filename: str
    ) -> str:
        """썸네일용 객체 키 생성"""
        file_extension = Path(original_filename).suffix.lower()
        timestamp = datetime.now().strftime("%Y/%m/%d")
        return f"thumbnails/{timestamp}/{file_id}_thumb.jpg"

    def _generate_image_url(self, object_key: str) -> str:
        """이미지 URL 생성"""
        settings = get_settings()
        protocol = "https" if settings.minio_secure else "http"
        return f"{protocol}://{settings.minio_endpoint}/{self.bucket_name}/{object_key}"


# 전역 인스턴스 (싱글톤 패턴)
_minio_uploader = None


def get_minio_uploader() -> MinIOUploader:
    """MinIO 업로더 인스턴스 반환 (싱글톤)"""
    global _minio_uploader
    if _minio_uploader is None:
        _minio_uploader = MinIOUploader()
    return _minio_uploader


# 편의 함수들
async def upload_image_to_minio(file: UploadFile):
    """
    이미지를 MinIO에 업로드하는 편의 함수

    Args:
        file: 업로드할 파일 객체

    Returns:
        tuple[str, str]: (파일 ID, 이미지 URL)
    """
    uploader = get_minio_uploader()
    return await uploader.upload_image(file)


async def upload_image_with_thumbnail_to_minio(
    file: UploadFile,
    thumbnail_size: tuple[int, int] = FileConstants.THUMBNAIL_SIZE,
):
    """
    이미지와 썸네일을 MinIO에 업로드하는 편의 함수

    Args:
        file: 업로드할 파일 객체
        thumbnail_size: 썸네일 크기 (기본값: 150x150)

    Returns:
        tuple[str, str, str]: (파일 ID, 원본 이미지 URL, 썸네일 URL)
    """
    uploader = get_minio_uploader()
    return await uploader.upload_image_with_thumbnail(file, thumbnail_size)


def delete_image_from_minio(object_key: str) -> bool:
    """
    MinIO에서 이미지를 삭제하는 편의 함수

    Args:
        object_key: 삭제할 객체의 키

    Returns:
        bool: 삭제 성공 여부
    """
    uploader = get_minio_uploader()
    return uploader.delete_image(object_key)


def get_image_url_from_minio(object_key: str) -> str:
    """
    MinIO 이미지 URL을 생성하는 편의 함수

    Args:
        object_key: 객체 키

    Returns:
        str: 이미지 접근 URL
    """
    uploader = get_minio_uploader()
    return uploader.get_image_url(object_key)
