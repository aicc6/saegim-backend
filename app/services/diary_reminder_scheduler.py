"""
개인화된 다이어리 리마인더 스케줄러
사용자별 설정(시간, 요일)에 맞춰 자동으로 다이어리 작성 알림을 발송하는 백그라운드 서비스
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.fcm import NotificationSettings
from app.models.user import User
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class DiaryReminderScheduler:
    """개인화된 다이어리 리마인더 스케줄러"""

    @staticmethod
    async def get_users_for_reminder_time(
        time: str, day: str, session: Session
    ) -> list[User]:
        """
        특정 시간/요일에 알림받을 사용자 조회

        Args:
            time: HH:MM 형식의 시간 (예: "21:00")
            day: 요일 (mon, tue, wed, thu, fri, sat, sun)
            session: DB 세션

        Returns:
            알림을 받아야 할 사용자 리스트
        """
        try:
            # 기본 쿼리: 다이어리 리마인더가 활성화되어 있고 해당 시간에 알림받는 사용자
            base_query = (
                select(User)
                .join(NotificationSettings)
                .where(
                    and_(
                        NotificationSettings.diary_reminder_enabled.is_(True),
                        NotificationSettings.diary_reminder_time == time,
                    )
                )
            )

            # 요일 조건 추가
            # diary_reminder_days가 None이면 매일, 빈 배열이면 매일, 특정 요일이 있으면 해당 요일만
            day_condition = or_(
                NotificationSettings.diary_reminder_days.is_(None),  # 매일 (기본값)
                func.jsonb_array_length(NotificationSettings.diary_reminder_days)
                == 0,  # 매일 (빈 배열)
                NotificationSettings.diary_reminder_days.contains([day]),  # 특정 요일
            )

            final_query = base_query.where(day_condition)
            result = session.execute(final_query)
            users = result.scalars().all()

            logger.info(
                f"시간 {time}, 요일 {day}에 알림받을 사용자 {len(users)}명 조회됨"
            )
            return list(users)

        except Exception as e:
            logger.error(f"리마인더 대상 사용자 조회 실패: {str(e)}")
            return []

    @staticmethod
    async def should_send_reminder(user_id: UUID, session: Session) -> bool:
        """
        중복 발송 방지를 위한 체크
        최근 24시간 내에 diary_reminder 타입의 알림을 보낸 적이 있는지 확인

        Args:
            user_id: 사용자 ID
            session: DB 세션

        Returns:
            True: 알림 발송 가능, False: 중복 발송 방지
        """
        try:
            from app.models.fcm import NotificationHistory

            # 24시간 전 시간 계산
            yesterday = datetime.now(UTC) - timedelta(hours=24)

            # 최근 24시간 내 diary_reminder 알림 이력 확인
            stmt = select(NotificationHistory).where(
                and_(
                    NotificationHistory.user_id == user_id,
                    NotificationHistory.notification_type == "diary_reminder",
                    NotificationHistory.created_at > yesterday,
                    NotificationHistory.status == "sent",
                )
            )

            result = session.execute(stmt).scalar_one_or_none()

            if result:
                logger.info(f"User {user_id}: 24시간 내 알림 발송 이력 있음, 스킵")
                return False

            return True

        except Exception as e:
            logger.error(f"중복 발송 체크 실패 (User: {user_id}): {str(e)}")
            # 에러 시 안전하게 발송하지 않음
            return False

    @staticmethod
    async def process_diary_reminders():
        """
        현재 시간에 맞는 사용자들에게 다이어리 리마인더 발송
        스케줄러에서 주기적으로 호출되는 메인 함수
        """
        try:
            # 현재 시간 정보 가져오기
            now = datetime.now(UTC)
            current_time = now.strftime("%H:%M")
            # 요일을 소문자 3자리로 변환 (mon, tue, wed, thu, fri, sat, sun)
            current_day = now.strftime("%a").lower()

            logger.info(f"다이어리 리마인더 처리 시작: {current_time} ({current_day})")

            # DB 세션 생성
            session = next(get_session())
            try:
                # 현재 시간에 알림받을 사용자 조회
                users = await DiaryReminderScheduler.get_users_for_reminder_time(
                    current_time, current_day, session
                )

                if not users:
                    logger.info("현재 시간에 알림받을 사용자가 없습니다.")
                    return

                # 각 사용자에게 알림 발송
                success_count = 0
                skip_count = 0
                error_count = 0

                for user in users:
                    try:
                        # 중복 발송 체크
                        if not await DiaryReminderScheduler.should_send_reminder(
                            user.id, session
                        ):
                            skip_count += 1
                            continue

                        # 알림 발송
                        result = await NotificationService.send_diary_reminder(user.id)

                        if result.success_count > 0:
                            success_count += 1
                            logger.debug(f"User {user.id}: 다이어리 리마인더 발송 성공")
                        else:
                            error_count += 1
                            logger.warning(
                                f"User {user.id}: 다이어리 리마인더 발송 실패"
                            )

                    except Exception as e:
                        error_count += 1
                        logger.error(
                            f"User {user.id} 다이어리 리마인더 발송 중 오류: {str(e)}"
                        )

                # 결과 로깅
                logger.info(
                    f"다이어리 리마인더 처리 완료: "
                    f"성공 {success_count}명, 스킵 {skip_count}명, 실패 {error_count}명"
                )

            finally:
                session.close()

        except Exception as e:
            logger.error(f"다이어리 리마인더 처리 중 전체 오류: {str(e)}")


# 스케줄러 설정을 위한 함수
def setup_diary_reminder_scheduler():
    """
    다이어리 리마인더 스케줄러 설정

    이 함수를 애플리케이션 시작 시 호출하여 스케줄러를 설정합니다.
    실제 스케줄러 구현체(APScheduler, Celery 등)에 따라 구현이 달라질 수 있습니다.
    """

    # APScheduler 사용 예시
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = AsyncIOScheduler()

        # 매 10분마다 실행 (더 정확한 시간 처리를 위해)
        scheduler.add_job(
            DiaryReminderScheduler.process_diary_reminders,
            trigger=CronTrigger(minute="*/10"),  # 매 10분 (00, 10, 20, 30, 40, 50분)
            id="diary_reminder_job",
            name="개인화된 다이어리 리마인더 발송",
            max_instances=1,  # 동시에 하나의 인스턴스만 실행
            coalesce=True,  # 누락된 작업들을 하나로 합침
        )

        logger.info("다이어리 리마인더 스케줄러가 설정되었습니다.")
        return scheduler

    except ImportError:
        logger.warning("APScheduler가 설치되지 않아 스케줄러를 설정할 수 없습니다.")
        return None
    except Exception as e:
        logger.error(f"다이어리 리마인더 스케줄러 설정 실패: {str(e)}")
        return None


# Celery 사용 예시 (선택적)
def setup_celery_diary_reminder():
    """
    Celery를 사용한 다이어리 리마인더 작업 설정
    """
    try:
        # Celery 앱이 이미 설정되어 있다고 가정
        # 실제로는 메인 애플리케이션에서 설정된 Celery 인스턴스를 사용
        # periodic task로 등록
        # @celery.task
        # async def diary_reminder_task():
        #     await DiaryReminderScheduler.process_diary_reminders()

        logger.info("Celery 다이어리 리마인더 작업이 설정되었습니다.")

    except ImportError:
        logger.warning("Celery가 설치되지 않아 작업을 설정할 수 없습니다.")
    except Exception as e:
        logger.error(f"Celery 다이어리 리마인더 작업 설정 실패: {str(e)}")
