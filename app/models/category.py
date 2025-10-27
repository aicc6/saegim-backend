"""다이어리 카테고리 모델"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.diary import DiaryEntry
    from app.models.user import User


class DiaryCategory(Base):
    """사용자 정의 다이어리 카테고리"""

    __tablename__ = "diary_categories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="diary_categories")
    diaries: Mapped[list[DiaryEntry]] = relationship(
        "DiaryEntry", back_populates="category", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_diary_categories_user_id_name"),
    )

