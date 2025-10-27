from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

if TYPE_CHECKING:
    from app.models.ai_usage_log import AIUsageLog
    from app.models.category import DiaryCategory
    from app.models.diary import DiaryEntry
    from app.models.emotion_stats import EmotionStats
    from app.models.fcm import FCMToken, NotificationHistory, NotificationSettings
    from app.models.notification import Notification
    from app.models.oauth_token import OAuthToken
    from app.models.password_reset_token import PasswordResetToken

from app.models.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("nickname", name="uq_users_nickname"),
        UniqueConstraint("provider", "provider_id", name="uq_users_provider_pid"),
        CheckConstraint(
            "account_type IN ('social','email')", name="ck_users_account_type"
        ),
        CheckConstraint(
            "(provider IS NULL OR provider IN ('google','kakao','naver'))",
            name="ck_users_provider",
        ),
        Index("idx_users_provider", "provider", "provider_id"),
        Index("idx_account_type", "account_type"),
        # partial index: WHERE deleted_at IS NULL
        Index(
            "idx_users_active",
            "is_active",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_type: Mapped[str] = mapped_column(
        String(6), nullable=False, default="social"
    )
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 관계 정의 - SQLAlchemy 2.0 방식
    oauth_tokens: Mapped[list[OAuthToken]] = relationship(
        back_populates="user", lazy="select"
    )
    reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user", lazy="select"
    )
    diaries: Mapped[list[DiaryEntry]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )
    diary_categories: Mapped[list[DiaryCategory]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )

    # FCM 관련 관계
    fcm_tokens: Mapped[list[FCMToken]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )
    notification_settings: Mapped[NotificationSettings | None] = relationship(
        back_populates="user",
        lazy="select",
        uselist=False,
        cascade="all, delete-orphan",
    )
    notification_history: Mapped[list[NotificationHistory]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )

    # 새로 추가된 관계들
    emotion_stats: Mapped[list[EmotionStats]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )
    ai_usage_logs: Mapped[list[AIUsageLog]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )
