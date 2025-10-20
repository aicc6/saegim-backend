"""
앱 버전 관리 모델
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.models.base import Base


class PlatformType(str, Enum):
    """플랫폼 타입"""

    IOS = "ios"
    ANDROID = "android"


class AppVersion(Base):
    """앱 버전 테이블 모델"""

    __tablename__ = "app_versions"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    version_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="버전명 (예: 1.0.0)"
    )
    platform: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="플랫폼 (ios, android)"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="버전 설명 및 변경사항"
    )
    file_path: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="MinIO 파일 경로"
    )
    file_size: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="파일 크기 (bytes)"
    )
    file_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="원본 파일명"
    )
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="필수 업데이트 여부"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="활성화 여부"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<AppVersion(id={self.id}, version={self.version_name}, "
            f"platform={self.platform})>"
        )
