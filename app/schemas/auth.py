import re
from typing import Any

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.base import BaseResponse


# registration
class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Any):
        # None 값 체크
        if v is None:
            raise ValueError("비밀번호는 필수입니다")

        # 빈 문자열 체크
        if not v or not isinstance(v, str):
            raise ValueError("비밀번호는 유효한 문자열이어야 합니다")

        if len(v) < 9:
            raise ValueError("비밀번호는 9자 이상이어야 합니다")

        # 영문, 숫자, 특수문자 포함 검사
        has_letter = bool(re.search(r"[a-zA-Z]", v))
        has_number = bool(re.search(r"\d", v))
        has_special = bool(re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>/?]', v))

        if not (has_letter and has_number and has_special):
            raise ValueError("비밀번호는 영문, 숫자, 특수문자를 모두 포함해야 합니다")

        return v

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: Any):
        # None 값 체크
        if v is None:
            raise ValueError("닉네임은 필수입니다")

        # 빈 문자열 체크
        if not v or not isinstance(v, str):
            raise ValueError("닉네임은 유효한 문자열이어야 합니다")

        if len(v) < 2 or len(v) > 10:
            raise ValueError("닉네임은 2-10자 사이여야 합니다")

        if not re.match(r"^[가-힣a-zA-Z]+$", v):
            raise ValueError("닉네임은 한글과 영문만 사용 가능합니다")

        return v


class SignUpResponseData(BaseModel):
    user_id: str
    email: str
    nickname: str
    message: str


class SignUpResponse(BaseResponse[SignUpResponseData]):
    pass


class EmailVerificationRequest(BaseModel):
    email: EmailStr


class EmailVerificationConfirmRequest(BaseModel):
    email: EmailStr
    verification_code: str
