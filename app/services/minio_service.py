"""
MinIO 스토리지 서비스
"""

import asyncio
import logging
from datetime import timedelta
from functools import lru_cache
from io import BytesIO
from typing import Any

from fastapi import UploadFile
from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)


class MinioService:
    """MinIO 스토리지 서비스"""

    def __init__(self) -> None:
        """MinIO 클라이언트 초기화"""
        self.client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket_name = settings.minio_bucket_name
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> None:
        """버킷 존재 확인 및 생성"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"MinIO 버킷 생성됨: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"MinIO 버킷 확인 실패: {e}")
            raise

    async def upload_file(
        self,
        file: UploadFile,
        object_name: str,
        content_type: str | None = None,
    ) -> tuple[str, int]:
        """
        파일을 MinIO에 업로드

        Args:
            file: 업로드할 파일
            object_name: MinIO에 저장될 객체명
            content_type: 파일의 Content-Type

        Returns:
            tuple[str, int]: (파일 경로, 파일 크기)
        """
        try:
            # 파일 내용을 메모리로 읽기
            file_content = await file.read()
            file_size = len(file_content)

            # BytesIO로 변환
            file_data = BytesIO(file_content)

            # 비동기 실행을 위해 sync 함수를 executor로 실행
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.put_object(
                    bucket_name=self.bucket_name,
                    object_name=object_name,
                    data=file_data,
                    length=file_size,
                    content_type=content_type
                    or file.content_type
                    or "application/octet-stream",
                ),
            )

            logger.info(f"파일 업로드 성공: {object_name} ({file_size} bytes)")
            return object_name, file_size

        except S3Error as e:
            logger.error(f"MinIO 파일 업로드 실패: {e}")
            raise
        finally:
            # 파일 포인터를 처음으로 되돌리기
            await file.seek(0)

    async def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
        custom_filename: str | None = None,
    ) -> str:
        """
        파일 다운로드를 위한 사전 서명된 URL 생성

        Args:
            object_name: MinIO 객체명
            expires: URL 만료 시간
            custom_filename: 커스텀 다운로드 파일명 (None이면 원본 파일명 사용)

        Returns:
            str: 사전 서명된 URL
        """
        try:
            loop = asyncio.get_event_loop()

            # response_headers 설정 (커스텀 파일명이 있는 경우)
            response_headers = None
            if custom_filename:
                response_headers = {
                    "response-content-disposition": f'attachment; filename="{custom_filename}"'
                }

            url = await loop.run_in_executor(
                None,
                lambda: self.client.presigned_get_object(
                    bucket_name=self.bucket_name,
                    object_name=object_name,
                    expires=expires,
                    response_headers=response_headers,
                ),
            )
            return url
        except S3Error as e:
            logger.error(f"MinIO presigned URL 생성 실패: {e}")
            raise

    async def delete_file(self, object_name: str) -> None:
        """
        MinIO에서 파일 삭제

        Args:
            object_name: 삭제할 객체명
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.remove_object(
                    bucket_name=self.bucket_name,
                    object_name=object_name,
                ),
            )
            logger.info(f"파일 삭제 성공: {object_name}")
        except S3Error as e:
            logger.error(f"MinIO 파일 삭제 실패: {e}")
            raise

    async def file_exists(self, object_name: str) -> bool:
        """
        파일 존재 여부 확인

        Args:
            object_name: 확인할 객체명

        Returns:
            bool: 존재 여부
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.stat_object(
                    bucket_name=self.bucket_name,
                    object_name=object_name,
                ),
            )
            return True
        except S3Error:
            return False

    async def get_file_info(self, object_name: str) -> dict[str, Any]:
        """
        파일 정보 조회

        Args:
            object_name: 객체명

        Returns:
            dict: 파일 정보
        """
        try:
            loop = asyncio.get_event_loop()
            stat = await loop.run_in_executor(
                None,
                lambda: self.client.stat_object(
                    bucket_name=self.bucket_name,
                    object_name=object_name,
                ),
            )
            return {
                "size": stat.size,
                "etag": stat.etag,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "metadata": stat.metadata,
            }
        except S3Error as e:
            logger.error(f"MinIO 파일 정보 조회 실패: {e}")
            raise


@lru_cache
def get_minio_service() -> MinioService:
    """MinIO 서비스 싱글톤 인스턴스 반환"""
    return MinioService()
