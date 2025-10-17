"""
트랜잭션 관리 컨텍스트 매니저
데이터베이스 세션의 자동 커밋/롤백을 제공
"""

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import ParamSpec, TypeVar

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class TransactionManager:
    """트랜잭션 관리 유틸리티 클래스"""

    @staticmethod
    @contextmanager
    def transaction(session: Session) -> Generator[Session, None, None]:
        """동기 트랜잭션 컨텍스트 매니저

        Args:
            session: 데이터베이스 세션

        Yields:
            Session: 트랜잭션이 관리되는 세션
        """
        try:
            yield session
            session.commit()
            logger.info("Transaction committed successfully")
        except Exception as e:
            session.rollback()
            logger.error(f"Transaction rolled back due to error: {e}")
            raise

    P = ParamSpec("P")
    R = TypeVar("R")

    @staticmethod
    def safe_execute(
        session: Session,
        operation: Callable[P, R],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        """트랜잭션 안전 실행 (동기)

        Args:
            session: 데이터베이스 세션
            operation: 실행할 함수 (임의의 시그니처)
            *args, **kwargs: 함수 인자들

        Returns:
            R: 함수 실행 결과의 구체적 타입
        """
        with TransactionManager.transaction(session):
            return operation(*args, **kwargs)
