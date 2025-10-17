"""
통일된 서비스 기본 클래스 (리팩토링됨)
중복된 트랜잭션 관리 코드 제거 및 컨텍스트 매니저 통합
"""

import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class BaseService:
    """모든 서비스의 기본 클래스"""

    def __init__(self, db: Session | None = None):
        """
        서비스 초기화

        Args:
            db: 데이터베이스 세션 (Session)
        """
        if not db:
            raise ValueError(f"Database session is required {__name__}")
        # 타입 체커를 위한 명시적 어서션
        assert isinstance(db, Session), f"{__name__} requires a Session instance"

        self._db = db
