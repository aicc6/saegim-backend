"""
이메일 서비스
실제 이메일 발송을 위한 유틸리티
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EmailService:
    def __init__(self):
        # SMTP 설정 (우선순위)
        self.smtp_server = settings.smtp_server
        self.smtp_port = settings.smtp_port
        self.smtp_username = settings.smtp_username
        self.smtp_password = settings.smtp_password
        self.from_email = settings.from_email

        # SendGrid 설정 (fallback)
        self.sendgrid_api_key = settings.sendgrid_api_key
        self.sendgrid_from_email = settings.sendgrid_from_email

    async def send_verification_email(
        self, to_email: str, verification_code: str, email_type: str = "signup"
    ) -> bool:
        """
        이메일 인증 코드 발송

        Args:
            to_email: 수신자 이메일
            verification_code: 인증 코드
            email_type: 이메일 타입 (signup, email_change)

        Returns:
            발송 성공 여부
        """
        try:
            # SMTP 설정이 있으면 SMTP 사용 (우선순위)
            if self.smtp_server and self.smtp_username and self.smtp_password:
                return await self._send_with_smtp(
                    to_email, verification_code, email_type
                )
            # SMTP 설정이 없으면 SendGrid 사용 (fallback)
            elif self.sendgrid_api_key:
                return await self._send_with_sendgrid(
                    to_email, verification_code, email_type
                )
            else:
                logger.error("No email service configured (SMTP or SendGrid)")
                return False

        except Exception as e:
            logger.error(f"Verification email sending failed: {to_email} - {e}")
            return False

    async def send_email_change_verification(
        self, to_email: str, verification_url: str, current_email: str
    ) -> bool:
        """
        이메일 변경 인증 URL 발송

        Args:
            to_email: 새로운 이메일 주소
            verification_url: 인증 URL
            current_email: 현재 이메일 주소

        Returns:
            발송 성공 여부
        """
        try:
            # SMTP 설정이 있으면 SMTP 사용 (우선순위)
            if self.smtp_server and self.smtp_username and self.smtp_password:
                return await self._send_email_change_with_smtp(
                    to_email, verification_url, current_email
                )
            # SMTP 설정이 없으면 SendGrid 사용 (fallback)
            elif self.sendgrid_api_key:
                return await self._send_email_change_with_sendgrid(
                    to_email, verification_url, current_email
                )
            else:
                logger.error("No email service configured (SMTP or SendGrid)")
                return False

        except Exception as e:
            logger.error(f"Email change verification sending failed: {to_email} - {e}")
            return False

    async def send_email(
        self, to_email: str, subject: str, body: str, html: bool = False
    ) -> bool:
        """
        일반 이메일 발송

        Args:
            to_email: 수신자 이메일
            subject: 이메일 제목
            body: 이메일 내용
            html: HTML 이메일 여부 (기본값: False)

        Returns:
            발송 성공 여부
        """
        try:
            # SMTP 설정이 있으면 SMTP 사용 (우선순위)
            if self.smtp_server and self.smtp_username and self.smtp_password:
                return await self._send_general_with_smtp(to_email, subject, body, html)
            # SMTP 설정이 없으면 SendGrid 사용 (fallback)
            elif self.sendgrid_api_key:
                return await self._send_general_with_sendgrid(
                    to_email, subject, body, html
                )
            else:
                logger.error("No email service configured (SMTP or SendGrid)")
                return False

        except Exception as e:
            logger.error(f"General email sending failed: {to_email} - {e}")
            return False

    async def _send_with_sendgrid(
        self, to_email: str, verification_code: str, email_type: str = "signup"
    ) -> bool:
        """SendGrid를 사용한 이메일 발송"""
        try:
            import httpx

            # 디버깅을 위한 로그 추가
            logger.info(f"SendGrid sender email: {self.sendgrid_from_email}")
            logger.info(f"Recipient email: {to_email}")

            # SendGrid API 엔드포인트
            url = "https://api.sendgrid.com/v3/mail/send"

            # 이메일 타입에 따른 제목과 내용
            if email_type == "restore":
                subject = "[Saegim] 계정 복구 인증"
                html_content = f"""
                <html>
                <body>
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #5C8D89;">Saegim 계정 복구 인증</h2>
                        <p>안녕하세요! Saegim 서비스의 계정 복구 요청이 있었습니다.</p>
                        <p>아래 인증 코드를 입력하여 계정 복구를 완료해주세요.</p>

                        <div style="background-color: #f5f5f5; padding: 20px; text-align: center; margin: 20px 0;">
                            <h3 style="color: #5C8D89; font-size: 24px; letter-spacing: 5px;">{verification_code}</h3>
                        </div>

                        <p><strong>이 인증 코드는 10분 후에 만료됩니다.</strong></p>

                        <p>본인이 요청하지 않은 경우 이 이메일을 무시하세요.</p>

                        <hr style="margin: 30px 0;">
                        <p style="color: #666; font-size: 12px;">
                            이 이메일은 Saegim 서비스에서 발송되었습니다.<br>
                            문의사항이 있으시면 고객센터에 연락해주세요.
                        </p>
                    </div>
                </body>
                </html>
                """
            elif email_type == "email_change":
                subject = "[Saegim] 이메일 변경 인증"
                html_content = f"""
                <html>
                <body>
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #5C8D89;">Saegim 이메일 변경 인증</h2>
                        <p>안녕하세요! Saegim 서비스의 이메일 변경 요청이 있었습니다.</p>
                        <p>아래 인증 코드를 입력하여 이메일 변경을 완료해주세요.</p>

                        <div style="background-color: #f5f5f5; padding: 20px; text-align: center; margin: 20px 0;">
                            <h3 style="color: #5C8D89; font-size: 24px; letter-spacing: 5px;">{verification_code}</h3>
                        </div>

                        <p><strong>이 인증 코드는 10분 후에 만료됩니다.</strong></p>

                        <p>본인이 요청하지 않은 경우 이 이메일을 무시하세요.</p>

                        <hr style="margin: 30px 0;">
                        <p style="color: #666; font-size: 12px;">
                            이 이메일은 Saegim 서비스에서 발송되었습니다.<br>
                            문의사항이 있으시면 고객센터에 연락해주세요.
                        </p>
                    </div>
                </body>
                </html>
                """
            else:
                subject = "[Saegim] 이메일 인증 코드"
                html_content = f"""
                <html>
                <body>
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #5C8D89;">Saegim 이메일 인증</h2>
                        <p>안녕하세요! Saegim 서비스 회원가입을 환영합니다.</p>
                        <p>아래 인증 코드를 입력하여 이메일 인증을 완료해주세요.</p>

                        <div style="background-color: #f5f5f5; padding: 20px; text-align: center; margin: 20px 0;">
                            <h3 style="color: #5C8D89; font-size: 24px; letter-spacing: 5px;">{verification_code}</h3>
                        </div>

                        <p><strong>이 인증 코드는 10분 후에 만료됩니다.</strong></p>

                        <p>본인이 요청하지 않은 경우 이 이메일을 무시하세요.</p>

                        <hr style="margin: 30px 0;">
                        <p style="color: #666; font-size: 12px;">
                            이 이메일은 Saegim 서비스에서 발송되었습니다.<br>
                            문의사항이 있으시면 고객센터에 연락해주세요.
                        </p>
                    </div>
                </body>
                </html>
                """

            # SendGrid API 요청 데이터
            data = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": self.sendgrid_from_email},
                "subject": subject,
                "content": [{"type": "text/html", "value": html_content}],
            }

            # API 요청 헤더
            headers = {
                "Authorization": f"Bearer {self.sendgrid_api_key}",
                "Content-Type": "application/json",
            }

            # SendGrid API 호출
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=headers)

            if response.status_code == 202:
                logger.info(
                    f"SendGrid verification email sent successfully: {to_email}"
                )
                return True
            else:
                logger.error(
                    f"SendGrid API error: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"SendGrid email sending failed: {e}")
            logger.error(f"Error type: {type(e)}")
            logger.error(f"Error args: {e.args}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False

    async def _send_with_smtp(
        self, to_email: str, verification_code: str, email_type: str = "signup"
    ) -> bool:
        """SMTP를 사용한 이메일 발송"""
        try:
            # 이메일 타입에 따른 제목과 내용 설정
            if email_type == "restore":
                subject = "[Saegim] 계정 복구 인증"
                title = "Saegim 계정 복구 인증"
                description = "안녕하세요! Saegim 서비스의 계정 복구 요청이 있었습니다."
                instruction = "아래 인증 코드를 입력하여 계정 복구를 완료해주세요."
            elif email_type == "email_change":
                subject = "[Saegim] 이메일 변경 인증"
                title = "Saegim 이메일 변경 인증"
                description = (
                    "안녕하세요! Saegim 서비스의 이메일 변경 요청이 있었습니다."
                )
                instruction = "아래 인증 코드를 입력하여 이메일 변경을 완료해주세요."
            else:  # signup
                subject = "[Saegim] 이메일 인증 코드"
                title = "Saegim 이메일 인증"
                description = "안녕하세요! Saegim 서비스 회원가입을 환영합니다."
                instruction = "아래 인증 코드를 입력하여 이메일 인증을 완료해주세요."

            html_content = f"""
            <html>
            <body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #5C8D89;">{title}</h2>
                    <p>{description}</p>
                    <p>{instruction}</p>

                    <div style="background-color: #f5f5f5; padding: 20px; text-align: center; margin: 20px 0;">
                        <h3 style="color: #5C8D89; font-size: 24px; letter-spacing: 5px;">{verification_code}</h3>
                    </div>

                    <p><strong>이 인증 코드는 10분 후에 만료됩니다.</strong></p>

                    <p>본인이 요청하지 않은 경우 이 이메일을 무시하세요.</p>

                    <hr style="margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        이 이메일은 Saegim 서비스에서 발송되었습니다.<br>
                        문의사항이 있으시면 고객센터에 연락해주세요.
                    </p>
                </div>
            </body>
            </html>
            """

            # 이메일 메시지 생성
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            # HTML 내용 추가
            html_part = MIMEText(html_content, "html", "utf-8")
            msg.attach(html_part)

            # SMTP 서버 연결 및 이메일 발송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(
                f"SMTP verification email sent successfully: {to_email} (type: {email_type})"
            )
            return True

        except Exception as e:
            logger.error(f"SMTP email sending failed: {to_email} - {e}")
            return False

    async def send_welcome_email(self, to_email: str, nickname: str) -> bool:
        """
        회원가입 완료 환영 이메일 발송

        Args:
            to_email: 수신자 이메일
            nickname: 사용자 닉네임

        Returns:
            발송 성공 여부
        """
        try:
            # SMTP 설정이 있으면 SMTP 사용 (우선순위)
            if self.smtp_server and self.smtp_username and self.smtp_password:
                return await self._send_welcome_with_smtp(to_email, nickname)
            # SMTP 설정이 없으면 SendGrid 사용 (fallback)
            elif self.sendgrid_api_key:
                return await self._send_welcome_with_sendgrid(to_email, nickname)
            else:
                logger.error("No email service configured (SMTP or SendGrid)")
                return False

        except Exception as e:
            logger.error(f"Welcome email sending failed: {to_email} - {e}")
            return False

    async def send_password_reset_email(
        self, to_email: str, nickname: str, reset_url: str
    ) -> bool:
        """
        비밀번호 재설정 이메일 발송 (URL 링크 방식)

        Args:
            to_email: 수신자 이메일
            nickname: 사용자 닉네임
            reset_url: 비밀번호 재설정 URL

        Returns:
            발송 성공 여부
        """
        try:
            # SMTP 설정이 있으면 SMTP 사용 (우선순위)
            if self.smtp_server and self.smtp_username and self.smtp_password:
                return await self._send_password_reset_with_smtp(
                    to_email, nickname, reset_url
                )
            # SMTP 설정이 없으면 SendGrid 사용 (fallback)
            elif self.sendgrid_api_key:
                return await self._send_password_reset_with_sendgrid(
                    to_email, nickname, reset_url
                )
            else:
                logger.error("No email service configured (SMTP or SendGrid)")
                return False

        except Exception as e:
            logger.error(f"Password reset email sending failed: {to_email} - {e}")
            return False

    async def send_social_account_password_reset_error(
        self, to_email: str, nickname: str, provider: str, error_url: str
    ) -> bool:
        """
        소셜 계정 사용자 비밀번호 재설정 에러 이메일 발송

        Args:
            to_email: 수신자 이메일
            nickname: 사용자 닉네임
            provider: 소셜 제공자 (google, kakao, naver 등)
            error_url: 에러 페이지 URL

        Returns:
            발송 성공 여부
        """
        try:
            # SMTP 설정이 있으면 SMTP 사용 (우선순위)
            if self.smtp_server and self.smtp_username and self.smtp_password:
                return await self._send_social_error_with_smtp(
                    to_email, nickname, provider, error_url
                )
            # SMTP 설정이 없으면 SendGrid 사용 (fallback)
            elif self.sendgrid_api_key:
                return await self._send_social_error_with_sendgrid(
                    to_email, nickname, provider, error_url
                )
            else:
                logger.error("No email service configured (SMTP or SendGrid)")
                return False

        except Exception as e:
            logger.error(f"Social account error email sending failed: {to_email} - {e}")
            return False

    async def _send_welcome_with_sendgrid(self, to_email: str, nickname: str) -> bool:
        """SendGrid를 사용한 환영 이메일 발송"""
        try:
            import httpx

            url = "https://api.sendgrid.com/v3/mail/send"
            subject = "[Saegim] Saegim 서비스에 오신 것을 환영합니다!"

            html_content = f"""
            <html>
            <body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #5C8D89;">Saegim 서비스에 오신 것을 환영합니다!</h2>
                    <p>안녕하세요, <strong>{nickname}</strong>님!</p>
                    <p>Saegim 서비스 회원가입이 성공적으로 완료되었습니다.</p>

                    <div style="background-color: #f0f8f7; padding: 20px; margin: 20px 0; border-radius: 10px;">
                        <h3 style="color: #5C8D89;">Saegim에서 할 수 있는 것들</h3>
                        <ul>
                            <li>AI와 함께 감정 일기 작성하기</li>
                            <li>감정 분석 및 키워드 추출</li>
                            <li>월간 감정 리포트</li>
                            <li>개인화된 AI 스타일 설정</li>
                        </ul>
                    </div>

                    <p>지금 바로 Saegim을 시작해보세요!</p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{settings.frontend_url}"
                           style="background-color: #5C8D89; color: white; padding: 12px 30px;
                                  text-decoration: none; border-radius: 5px; display: inline-block;">
                            Saegim 시작하기
                        </a>
                    </div>

                    <hr style="margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        이 이메일은 Saegim 서비스에서 발송되었습니다.<br>
                        문의사항이 있으시면 고객센터에 연락해주세요.
                    </p>
                </div>
            </body>
            </html>
            """

            data = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": self.sendgrid_from_email},
                "subject": subject,
                "content": [{"type": "text/html", "value": html_content}],
            }

            headers = {
                "Authorization": f"Bearer {self.sendgrid_api_key}",
                "Content-Type": "application/json",
            }

            # SendGrid API 호출
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=headers)

            if response.status_code == 202:
                logger.info(f"SendGrid welcome email sent successfully: {to_email}")
                return True
            else:
                logger.error(
                    f"SendGrid API error: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"SendGrid welcome email sending failed: {e}")
            return False

    async def _send_welcome_with_smtp(self, to_email: str, nickname: str) -> bool:
        """기존 SMTP를 사용한 환영 이메일 발송"""
        try:
            subject = "[Saegim] Welcome to Saegim!"

            html_content = f"""
            <html>
            <body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #5C8D89;">Welcome to Saegim!</h2>
                    <p>Hello, <strong>{nickname}</strong>!</p>
                    <p>Your Saegim service registration has been completed successfully.</p>

                    <div style="background-color: #f0f8f7; padding: 20px; margin: 20px 0; border-radius: 10px;">
                        <h3 style="color: #5C8D89;">What you can do with Saegim</h3>
                        <ul>
                            <li>Write emotional diaries with AI</li>
                            <li>Emotion analysis and keyword extraction</li>
                            <li>Monthly emotion report</li>
                            <li>Personalized AI style settings</li>
                        </ul>
                    </div>

                    <p>Start using Saegim now!</p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{settings.frontend_url}"
                           style="background-color: #5C8D89; color: white; padding: 12px 30px;
                                  text-decoration: none; border-radius: 5px; display: inline-block;">
                            Start Saegim
                        </a>
                    </div>

                    <hr style="margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        This email was sent from Saegim service.<br>
                        If you have any questions, please contact our customer service.
                    </p>
                </div>
            </body>
            </html>
            """

            # 이메일 메시지 생성
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            # HTML 내용 추가
            html_part = MIMEText(html_content, "html", "utf-8")
            msg.attach(html_part)

            # SMTP 서버 연결 및 이메일 발송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"SMTP welcome email sent successfully: {to_email}")
            return True

        except Exception as e:
            logger.error(f"SMTP welcome email sending failed: {to_email} - {e}")
            return False

    async def _send_email_change_with_sendgrid(
        self, to_email: str, verification_url: str, current_email: str
    ) -> bool:
        """SendGrid를 사용한 이메일 변경 인증 URL 발송"""
        try:
            import httpx

            # SendGrid API 엔드포인트
            url = "https://api.sendgrid.com/v3/mail/send"

            # 이메일 제목과 내용
            subject = "[Saegim] 이메일 변경 인증"

            html_content = f"""
            <html>
            <body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #5C8D89;">Saegim 이메일 변경 인증</h2>
                    <p>안녕하세요! Saegim 서비스의 이메일 변경 요청이 있었습니다.</p>
                    <p><strong>현재 이메일:</strong> {current_email}</p>
                    <p><strong>변경할 이메일:</strong> {to_email}</p>
                    <p>아래 버튼을 클릭하여 이메일 변경을 완료해주세요.</p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{verification_url}"
                           style="background-color: #5C8D89; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                            이메일 변경 인증하기
                        </a>
                    </div>

                    <p style="color: #666; font-size: 14px;">
                        위 버튼이 작동하지 않는 경우, 아래 링크를 복사하여 브라우저에 붙여넣기 해주세요:<br>
                        <a href="{verification_url}" style="color: #5C8D89; word-break: break-all;">{verification_url}</a>
                    </p>

                    <p><strong>이 인증 링크는 30분 후에 만료됩니다.</strong></p>

                    <p>본인이 요청하지 않은 경우 이 이메일을 무시하세요.</p>

                    <hr style="margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        이 이메일은 Saegim 서비스에서 발송되었습니다.<br>
                        문의사항이 있으시면 고객센터에 연락해주세요.
                    </p>
                </div>
            </body>
            </html>
            """

            # SendGrid API 요청 데이터
            data = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": self.sendgrid_from_email},
                "subject": subject,
                "content": [{"type": "text/html", "value": html_content}],
            }

            # SendGrid API 호출
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=data,
                    headers={
                        "Authorization": f"Bearer {self.sendgrid_api_key}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code == 202:
                    logger.info(
                        f"Email change verification sent successfully to {to_email}"
                    )
                    return True
                else:
                    logger.error(
                        f"SendGrid API error: {response.status_code} - {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"SendGrid email change verification sending failed: {e}")
            return False

    async def _send_email_change_with_smtp(
        self, to_email: str, verification_url: str, current_email: str
    ) -> bool:
        """SMTP를 사용한 이메일 변경 인증 URL 발송 (fallback)"""
        try:
            # 이메일 제목과 내용
            subject = "[Saegim] 이메일 변경 인증"

            html_content = f"""
            <html>
            <body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #5C8D89;">Saegim 이메일 변경 인증</h2>
                    <p>안녕하세요! Saegim 서비스의 이메일 변경 요청이 있었습니다.</p>
                    <p><strong>현재 이메일:</strong> {current_email}</p>
                    <p><strong>변경할 이메일:</strong> {to_email}</p>
                    <p>아래 링크를 클릭하여 이메일 변경을 완료해주세요.</p>

                    <p><a href="{verification_url}" style="color: #5C8D89;">{verification_url}</a></p>

                    <p><strong>이 인증 링크는 30분 후에 만료됩니다.</strong></p>

                    <p>본인이 요청하지 않은 경우 이 이메일을 무시하세요.</p>
                </div>
            </body>
            </html>
            """

            # MIME 메시지 생성
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            # HTML 내용 추가
            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)

            # SMTP 서버 연결 및 이메일 발송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Email change verification sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"SMTP email change verification sending failed: {e}")
            return False

    async def _send_password_reset_with_sendgrid(
        self, to_email: str, nickname: str, reset_url: str
    ) -> bool:
        """SendGrid를 사용한 비밀번호 재설정 이메일 발송"""
        try:
            import httpx

            # SendGrid API 엔드포인트
            url = "https://api.sendgrid.com/v3/mail/send"

            subject = "[Saegim] 비밀번호 재설정"
            html_content = f"""
            <html>
            <body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #5C8D89;">Saegim 비밀번호 재설정</h2>
                    <p>안녕하세요, <strong>{nickname}</strong>님!</p>
                    <p>Saegim 서비스에서 비밀번호 재설정 요청이 있었습니다.</p>
                    <p>아래 링크를 클릭하여 새로운 비밀번호를 설정해주세요.</p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_url}" style="background-color: #5C8D89; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            비밀번호 재설정하기
                        </a>
                    </div>

                    <p><strong>이 링크는 1시간 후에 만료됩니다.</strong></p>
                    <p>본인이 요청하지 않은 경우 이 이메일을 무시하세요.</p>

                    <hr style="margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        이 이메일은 Saegim 서비스에서 발송되었습니다.<br>
                        문의사항이 있으시면 고객센터에 연락해주세요.
                    </p>
                </div>
            </body>
            </html>
            """

            # SendGrid API 요청 데이터
            data = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": self.sendgrid_from_email},
                "subject": subject,
                "content": [{"type": "text/html", "value": html_content}],
            }

            # SendGrid API 호출
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=data,
                    headers={
                        "Authorization": f"Bearer {self.sendgrid_api_key}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code == 202:
                    logger.info(f"Password reset email sent successfully to {to_email}")
                    return True
                else:
                    logger.error(
                        f"SendGrid API error: {response.status_code} - {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"SendGrid password reset email sending failed: {e}")
            return False

    async def _send_password_reset_with_smtp(
        self, to_email: str, nickname: str, reset_url: str
    ) -> bool:
        """SMTP를 사용한 비밀번호 재설정 이메일 발송 (fallback)"""
        try:
            subject = "[Saegim] 비밀번호 재설정"

            html_content = f"""
            <html>
            <body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #5C8D89;">Saegim 비밀번호 재설정</h2>
                    <p>안녕하세요, <strong>{nickname}</strong>님!</p>
                    <p>Saegim 서비스에서 비밀번호 재설정 요청이 있었습니다.</p>
                    <p>아래 링크를 클릭하여 새로운 비밀번호를 설정해주세요.</p>

                    <p><a href="{reset_url}" style="color: #5C8D89;">{reset_url}</a></p>

                    <p><strong>이 링크는 1시간 후에 만료됩니다.</strong></p>
                    <p>본인이 요청하지 않은 경우 이 이메일을 무시하세요.</p>
                </div>
            </body>
            </html>
            """

            # MIME 메시지 생성
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            # HTML 내용 추가
            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)

            # SMTP 서버 연결 및 이메일 발송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Password reset email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"SMTP password reset email sending failed: {e}")
            return False

    async def _send_social_error_with_sendgrid(
        self, to_email: str, nickname: str, provider: str, error_url: str
    ) -> bool:
        """SendGrid를 사용한 소셜 계정 에러 이메일 발송"""
        try:
            import httpx

            # SendGrid API 엔드포인트
            url = "https://api.sendgrid.com/v3/mail/send"

            subject = "[Saegim] 비밀번호 재설정 안내"
            html_content = f"""
            <html>
            <body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #5C8D89;">Saegim 비밀번호 재설정 안내</h2>
                    <p>안녕하세요, <strong>{nickname}</strong>님!</p>
                    <p>Saegim 서비스에서 비밀번호 재설정 요청이 있었습니다.</p>
                    <p><strong>현재 {provider} 소셜 계정으로 가입되어 계십니다.</strong></p>

                    <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="color: #856404; margin-top: 0;">⚠️ 소셜 계정 사용자 안내</h3>
                        <p style="color: #856404; margin-bottom: 0;">
                            소셜 계정으로 가입하신 경우, 비밀번호는 해당 서비스에서 직접 관리해주세요.<br>
                            Saegim에서는 비밀번호 재설정이 불가능합니다.
                        </p>
                    </div>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{error_url}" style="background-color: #6c757d; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            자세한 안내 보기
                        </a>
                    </div>

                    <p>궁금한 점이 있으시면 고객센터에 문의해주세요.</p>

                    <hr style="margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        이 이메일은 Saegim 서비스에서 발송되었습니다.<br>
                        문의사항이 있으시면 고객센터에 연락해주세요.
                    </p>
                </div>
            </body>
            </html>
            """

            # SendGrid API 요청 데이터
            data = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": self.sendgrid_from_email},
                "subject": subject,
                "content": [{"type": "text/html", "value": html_content}],
            }

            # SendGrid API 호출
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=data,
                    headers={
                        "Authorization": f"Bearer {self.sendgrid_api_key}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code == 202:
                    logger.info(
                        f"Social account error email sent successfully to {to_email}"
                    )
                    return True
                else:
                    logger.error(
                        f"SendGrid API error: {response.status_code} - {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"SendGrid social error email sending failed: {e}")
            return False

    async def _send_social_error_with_smtp(
        self, to_email: str, nickname: str, provider: str, error_url: str
    ) -> bool:
        """SMTP를 사용한 소셜 계정 에러 이메일 발송 (fallback)"""
        try:
            subject = "[Saegim] 비밀번호 재설정 안내"

            html_content = f"""
            <html>
            <body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #5C8D89;">Saegim 비밀번호 재설정 안내</h2>
                    <p>안녕하세요, <strong>{nickname}</strong>님!</p>
                    <p>Saegim 서비스에서 비밀번호 재설정 요청이 있었습니다.</p>
                    <p><strong>현재 {provider} 소셜 계정으로 가입되어 계십니다.</strong></p>

                    <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="color: #856404; margin-top: 0;">⚠️ 소셜 계정 사용자 안내</h3>
                        <p style="color: #856404; margin-bottom: 0;">
                            소셜 계정으로 가입하신 경우, 비밀번호는 해당 서비스에서 직접 관리해주세요.<br>
                            Saegim에서는 비밀번호 재설정이 불가능합니다.
                        </p>
                    </div>

                    <p><a href="{error_url}" style="color: #5C8D89;">자세한 안내 보기</a></p>

                    <p>궁금한 점이 있으시면 고객센터에 문의해주세요.</p>
                </div>
            </body>
            </html>
            """

            # MIME 메시지 생성
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            # HTML 내용 추가
            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)

            # SMTP 서버 연결 및 이메일 발송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Social account error email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"SMTP social error email sending failed: {e}")
            return False

    async def _send_general_with_sendgrid(
        self, to_email: str, subject: str, body: str, html: bool = False
    ) -> bool:
        """SendGrid를 사용한 일반 이메일 발송"""
        try:
            import httpx

            # SendGrid API 엔드포인트
            url = "https://api.sendgrid.com/v3/mail/send"

            # 이메일 타입에 따른 content 설정
            if html:
                content_type = "text/html"
            else:
                content_type = "text/plain"

            # SendGrid API 요청 데이터
            data = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": self.sendgrid_from_email},
                "subject": subject,
                "content": [{"type": content_type, "value": body}],
            }

            # SendGrid API 호출
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=data,
                    headers={
                        "Authorization": f"Bearer {self.sendgrid_api_key}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code == 202:
                    logger.info(f"General email sent successfully to {to_email}")
                    return True
                else:
                    logger.error(
                        f"SendGrid API error: {response.status_code} - {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"SendGrid general email sending failed: {e}")
            return False

    async def _send_general_with_smtp(
        self, to_email: str, subject: str, body: str, html: bool = False
    ) -> bool:
        """SMTP를 사용한 일반 이메일 발송 (fallback)"""
        try:
            # MIME 메시지 생성
            if html:
                msg = MIMEText(body, "html")
            else:
                msg = MIMEText(body, "plain")

            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            # SMTP 서버 연결 및 이메일 발송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"General email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"SMTP general email sending failed: {e}")
            return False
