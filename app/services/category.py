"""다이어리 카테고리 서비스"""

import logging
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.transaction_manager import TransactionManager
from app.exceptions.category import (
    CategoryConflictException,
    CategoryNotFoundException,
    CategoryValidationException,
)
from app.models.category import DiaryCategory
from app.schemas.category import (
    DiaryCategoryCreateRequest,
    DiaryCategoryUpdateRequest,
)
from app.services.base import BaseService

logger = logging.getLogger(__name__)


class DiaryCategoryService(BaseService):
    """사용자 다이어리 카테고리 관리"""

    def __init__(self, db: Session):
        super().__init__(db)

    def list_categories(self, user_id: UUID) -> list[DiaryCategory]:
        stmt = (
            select(DiaryCategory)
            .where(DiaryCategory.user_id == user_id)
            .order_by(DiaryCategory.created_at.asc())
        )
        result = self._db.execute(stmt)
        categories = result.scalars().all()
        logger.debug("Fetched %d categories for user %s", len(categories), user_id)
        return categories

    def get_category(self, user_id: UUID, category_id: str) -> DiaryCategory:
        category = self.__fetch_category(category_id, user_id)
        return category

    def create_category(
        self, user_id: UUID, request: DiaryCategoryCreateRequest
    ) -> DiaryCategory:
        name = request.name.strip()
        if not name:
            raise CategoryValidationException(
                detail="카테고리 이름을 입력해 주세요.", field="name"
            )

        with TransactionManager.transaction(self._db) as tx:
            category = DiaryCategory(
                id=self.__generate_category_id(),
                user_id=user_id,
                name=name,
            )
            tx.add(category)
            try:
                tx.flush()
                tx.refresh(category)
            except IntegrityError as exc:
                logger.info(
                    "Duplicated category name detected for user %s: %s", user_id, name
                )
                raise CategoryConflictException(
                    field="name", detail="이미 존재하는 카테고리 이름입니다."
                ) from exc

        logger.info("Created category %s for user %s", category.id, user_id)
        return category

    def update_category(
        self, user_id: UUID, category_id: str, request: DiaryCategoryUpdateRequest
    ) -> DiaryCategory:
        name = request.name.strip()
        if not name:
            raise CategoryValidationException(
                detail="카테고리 이름을 입력해 주세요.", field="name"
            )

        with TransactionManager.transaction(self._db) as tx:
            category = self.__fetch_category(category_id, user_id, tx)
            category.name = name
            tx.add(category)
            try:
                tx.flush()
                tx.refresh(category)
            except IntegrityError as exc:
                logger.info(
                    "Duplicated category name detected for user %s: %s", user_id, name
                )
                raise CategoryConflictException(
                    field="name", detail="이미 존재하는 카테고리 이름입니다."
                ) from exc

        logger.info("Updated category %s for user %s", category_id, user_id)
        return category

    def delete_category(self, user_id: UUID, category_id: str) -> None:
        with TransactionManager.transaction(self._db) as tx:
            category = self.__fetch_category(category_id, user_id, tx)
            tx.delete(category)
            logger.info("Deleted category %s for user %s", category_id, user_id)

    def __fetch_category(
        self, category_id: str, user_id: UUID, tx: Optional[Session] = None
    ) -> DiaryCategory:
        stmt = select(DiaryCategory).where(
            DiaryCategory.id == category_id, DiaryCategory.user_id == user_id
        )
        result = (tx or self._db).execute(stmt)
        category = result.scalar_one_or_none()
        if category is None:
            logger.info(
                "Category not found for user %s: %s", user_id, category_id
            )
            raise CategoryNotFoundException(category_id)
        return category

    @staticmethod
    def __generate_category_id() -> str:
        return f"cat_{uuid4().hex[:24]}"
