"""
다이어리 비즈니스 로직 서비스 (캘린더용)
"""

import logging
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import SortOrder
from app.models.diary import DiaryEntry
from app.schemas.diary import DiaryCreateRequest, DiaryUpdateRequest
from app.services.base import BaseService
from app.utils.error_handlers import ErrorPatterns, database_transaction_handler
from app.utils.validators import extract_minio_object_key

logger = logging.getLogger(__name__)


class DiaryService(BaseService):
    """다이어리 비즈니스 로직 (캘린더용)"""

    def __init__(self, session: Session):
        super().__init__(session)
        self.session = session  # 기존 코드 호환성을 위해 유지

    def get_diaries(
        self,
        user_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        searchTerm: str | None = None,
        emotion: str | None = None,
        is_public: bool | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        sort_order: str = SortOrder.DESC.value,
    ) -> tuple[list[DiaryEntry], int]:
        """다이어리 목록 조회 (페이지네이션 포함)"""

        # 이미지 관계를 함께 로드하기 위해 selectinload 사용
        from sqlalchemy.orm import selectinload

        # 기본 쿼리 구성 - 이미지 관계 포함
        statement = select(DiaryEntry).options(selectinload(DiaryEntry.images))

        # 사용자별 필터링 (Soft Delete 제외)
        if user_id is not None:
            statement = statement.where(
                DiaryEntry.user_id == user_id, DiaryEntry.deleted_at.is_(None)
            )

        # 통합 검색 (제목 또는 내용)
        if searchTerm:
            statement = statement.where(
                (DiaryEntry.title.ilike(f"%{searchTerm}%"))
                | (DiaryEntry.content.ilike(f"%{searchTerm}%"))
            )

        # 감정별 필터링
        if emotion:
            statement = statement.where(DiaryEntry.user_emotion == emotion)

        # 공개 여부 필터링
        if is_public is not None:
            statement = statement.where(DiaryEntry.is_public == is_public)

        # 날짜 범위 필터링 (diary_date 우선, 없으면 created_at 사용)
        if start_date:
            statement = statement.where(
                func.coalesce(DiaryEntry.diary_date, func.date(DiaryEntry.created_at)) >= start_date
            )
        if end_date:
            statement = statement.where(
                func.coalesce(DiaryEntry.diary_date, func.date(DiaryEntry.created_at)) <= end_date
            )

        # 정렬 적용 (diary_date 우선, 없으면 created_at 사용)
        # 1차: diary_date (내림차순/오름차순)
        # 2차: created_at (내림차순/오름차순) - 같은 날짜 내에서 시간순 정렬
        if sort_order.lower() == SortOrder.DESC.value:
            statement = statement.order_by(
                func.coalesce(DiaryEntry.diary_date, func.date(DiaryEntry.created_at)).desc(),
                DiaryEntry.created_at.desc()  # 2차 정렬: 같은 날짜 내에서 최신순
            )
        else:
            statement = statement.order_by(
                func.coalesce(DiaryEntry.diary_date, func.date(DiaryEntry.created_at)).asc(),
                DiaryEntry.created_at.asc()  # 2차 정렬: 같은 날짜 내에서 오래된순
            )

        # 전체 개수 조회 (user_id 필터 적용, Soft Delete 제외)
        count_statement = select(func.count(DiaryEntry.id))
        if user_id is not None:
            count_statement = count_statement.where(
                DiaryEntry.user_id == user_id, DiaryEntry.deleted_at.is_(None)
            )

        result = self.session.execute(count_statement)
        total_count = result.scalar_one()

        # 페이지네이션 적용
        offset = (page - 1) * page_size
        statement = statement.offset(offset).limit(page_size)

        # 결과 조회
        result = self.session.execute(statement)
        diaries = result.scalars().all()

        return diaries, total_count

    def get_diary_by_id(
        self, diary_id: str, user_id: UUID | None = None
    ) -> DiaryEntry | None:
        """ID로 다이어리 조회 (Soft Delete 제외)"""
        statement = select(DiaryEntry).where(
            DiaryEntry.id == diary_id, DiaryEntry.deleted_at.is_(None)
        )

        if user_id is not None:
            statement = statement.where(DiaryEntry.user_id == user_id)

        result = self.session.execute(statement)
        return result.scalar_one_or_none()

    def get_diaries_by_date_range(
        self, user_id: UUID, start_date: date, end_date: date
    ) -> list[DiaryEntry]:
        """특정 날짜 범위의 다이어리 조회 (캘린더용) - 이미지 정보 포함"""
        # 이미지 관계를 함께 로드하기 위해 selectinload 사용
        from sqlalchemy.orm import selectinload

        statement = (
            select(DiaryEntry)
            .options(selectinload(DiaryEntry.images))
            .where(
                DiaryEntry.user_id == user_id,
                DiaryEntry.deleted_at.is_(None),
                func.coalesce(DiaryEntry.diary_date, func.date(DiaryEntry.created_at)) >= start_date,
                func.coalesce(DiaryEntry.diary_date, func.date(DiaryEntry.created_at)) <= end_date,
            )
            .order_by(
                func.coalesce(DiaryEntry.diary_date, func.date(DiaryEntry.created_at)).desc()
            )
        )

        result = self.session.execute(statement)
        return result.scalars().all()

    def create_diary(
        self, diary_create: DiaryCreateRequest, user_id: UUID
    ) -> DiaryEntry:
        """새로운 다이어리 생성"""

        try:
            # 새 다이어리 엔트리 생성 (실제 AI 데이터 사용)
            new_diary = DiaryEntry(
                user_id=user_id,
                title=diary_create.title,
                content=diary_create.content,
                user_emotion=diary_create.user_emotion,
                ai_emotion=diary_create.ai_emotion,
                ai_emotion_confidence=diary_create.ai_emotion_confidence,
                ai_generated_text=diary_create.ai_generated_text,
                keywords=diary_create.keywords,
                diary_date=diary_create.diary_date,
            )

            # 데이터베이스에 저장
            self.session.add(new_diary)
            self.session.commit()
            self.session.refresh(new_diary)

            # 업로드된 이미지가 있다면 Image 레코드 생성
            if diary_create.uploaded_images:
                from app.models.image import Image

                for image_data in diary_create.uploaded_images:
                    # uploaded_images의 각 항목을 Image 모델로 변환
                    new_image = Image(
                        diary_id=new_diary.id,
                        file_path=image_data.get("original_url"),
                        thumbnail_path=image_data.get("thumbnail_url"),
                        mime_type=image_data.get("mime_type"),
                        file_size=image_data.get("file_size"),
                        exif_removed=True,  # 이미 처리된 이미지이므로 True
                        created_at=datetime.now(UTC),
                    )
                    self.session.add(new_image)

                # 이미지 레코드들 저장
                self.session.commit()

            return new_diary

        except Exception as e:
            self.session.rollback()
            logger.error(f"다이어리 생성 실패 - user_id: {user_id}, error: {e}")
            raise

    def update_diary(
        self, diary_id: str, diary_update: DiaryUpdateRequest
    ) -> DiaryEntry | None:
        """다이어리 수정"""
        diary = self.get_diary_by_id(diary_id)

        if not diary:
            return None

        # 업데이트할 필드들만 수정
        update_data = diary_update.dict(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(diary, field):
                # keywords 필드는 JSONB 타입이므로 리스트 그대로 저장
                setattr(diary, field, value)

        # updated_at 필드 자동 업데이트
        diary.updated_at = datetime.now(UTC)

        # 데이터베이스에 저장
        self.session.add(diary)
        self.session.commit()
        self.session.refresh(diary)

        return diary

    def delete_diary(self, diary_id: str, user_id: UUID) -> bool:
        """다이어리 삭제 (Soft Delete) - 관련 이미지들도 MinIO에서 삭제"""
        diary = self.get_diary_by_id(diary_id, user_id)

        if not diary:
            return False

        with database_transaction_handler(
            self.session,
            ErrorPatterns.DIARY_DELETE_FAILED,
            log_context=f"다이어리 삭제 - diary_id: {diary_id}",
        ):
            # 다이어리와 관련된 이미지들 조회
            from app.models.image import Image
            from app.utils.minio_upload import get_minio_uploader

            stmt = select(Image).where(Image.diary_id == diary_id)
            result = self.session.execute(stmt)
            images = result.scalars().all()

            # MinIO에서 이미지 파일들 삭제
            if images:
                uploader = get_minio_uploader()

                for image in images:
                    # 원본 이미지 삭제
                    if image.file_path:
                        original_key = extract_minio_object_key(image.file_path)
                        if original_key:
                            uploader.delete_image(original_key)

                    # 썸네일 삭제
                    if image.thumbnail_path:
                        thumbnail_key = extract_minio_object_key(image.thumbnail_path)
                        if thumbnail_key:
                            uploader.delete_image(thumbnail_key)

                # 데이터베이스에서 이미지 레코드들 삭제
                for image in images:
                    self.session.delete(image)

            # Soft Delete: deleted_at 필드를 현재 시간으로 설정
            diary.deleted_at = datetime.now(UTC)

            # 데이터베이스에 저장
            self.session.add(diary)
            self.session.commit()

            return True
