"""
암호화 및 해싱 유틸리티
bcrypt(cost factor: 12)와 AES-256-GCM 암호화 지원
"""

import base64
import os
from typing import Optional

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

settings = get_settings()

# bcrypt 설정 (cost factor: 12)
BCRYPT_ROUNDS = 12


class PasswordHasher:
    """비밀번호 해싱 클래스 (bcrypt)"""

    @staticmethod
    def hash_password(password: str) -> str:
        """
        비밀번호를 bcrypt로 해싱 (cost factor: 12)

        Args:
            password: 평문 비밀번호

        Returns:
            해싱된 비밀번호
        """
        # None 값 체크
        if password is None:
            raise ValueError("비밀번호는 None일 수 없습니다")

        # 빈 문자열 체크
        if not isinstance(password, str):
            raise ValueError("비밀번호는 문자열이어야 합니다")

        # bcrypt.gensalt()로 salt 생성 (rounds=12)
        salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
        # 비밀번호를 bytes로 인코딩하고 해싱
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        # 결과를 string으로 디코딩하여 반환
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str | None) -> bool:
        """
        비밀번호 검증

        Args:
            plain_password: 평문 비밀번호
            hashed_password: 해싱된 비밀번호

        Returns:
            검증 결과
        """
        try:
            # None 값 체크
            if plain_password is None or hashed_password is None:
                return False

            # 빈 문자열 체크
            if not plain_password or not hashed_password:
                return False

            return bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except (ValueError, TypeError, AttributeError):
            return False

    @staticmethod
    def needs_update(hashed_password: str) -> bool:
        """
        해시가 업데이트가 필요한지 확인

        bcrypt 직접 사용 시 간단한 버전 체크

        Args:
            hashed_password: 해싱된 비밀번호

        Returns:
            업데이트 필요 여부
        """
        try:
            # $2b$ 버전이 아니거나 rounds가 다르면 업데이트 필요
            if not hashed_password.startswith("$2b$"):
                return True

            # rounds 체크 (예: $2b$12$...)
            parts = hashed_password.split("$")
            if len(parts) >= 3:
                try:
                    rounds = int(parts[2])
                    return rounds != BCRYPT_ROUNDS
                except ValueError:
                    return True
            return True
        except (AttributeError, IndexError):
            return True


class DataEncryption:
    """민감 데이터 암호화 클래스 (AES-256-GCM)"""

    def __init__(self, key: Optional[str] = None):
        """
        데이터 암호화 초기화

        Args:
            key: 암호화 키 (없으면 설정에서 가져옴)
        """
        if key is None:
            key = settings.encryption_key

        # 키를 32바이트로 변환
        self.key = self._derive_key(key)
        self.cipher = AESGCM(self.key)

    def _derive_key(self, key: str) -> bytes:
        """
        문자열 키를 32바이트 키로 변환

        Args:
            key: 문자열 키

        Returns:
            32바이트 키
        """
        # 키를 UTF-8로 인코딩하고 32바이트로 맞춤
        key_bytes = key.encode("utf-8")
        if len(key_bytes) >= 32:
            return key_bytes[:32]
        else:
            # 32바이트가 안 되면 패딩
            return key_bytes.ljust(32, b"\x00")

    def encrypt(self, plaintext: str) -> str:
        """
        데이터 암호화 (AES-256-GCM)

        Args:
            plaintext: 평문 데이터

        Returns:
            Base64 인코딩된 암호화 데이터 (nonce + ciphertext)
        """
        if not plaintext:
            return ""

        # None 값 체크
        if plaintext is None:
            return ""

        # 문자열 타입 체크
        if not isinstance(plaintext, str):
            raise ValueError("평문 데이터는 문자열이어야 합니다")

        # 96-bit nonce 생성 (GCM 권장)
        nonce = os.urandom(12)

        # 암호화
        ciphertext = self.cipher.encrypt(nonce, plaintext.encode("utf-8"), None)

        # nonce + ciphertext를 base64로 인코딩
        encrypted_data = nonce + ciphertext
        return base64.b64encode(encrypted_data).decode("utf-8")

    def decrypt(self, encrypted_data: str) -> str:
        """
        데이터 복호화

        Args:
            encrypted_data: Base64 인코딩된 암호화 데이터

        Returns:
            복호화된 평문 데이터

        Raises:
            ValueError: 복호화 실패 시
        """
        if not encrypted_data:
            return ""

        # None 값 체크
        if encrypted_data is None:
            return ""

        # 문자열 타입 체크
        if not isinstance(encrypted_data, str):
            raise ValueError("암호화된 데이터는 문자열이어야 합니다")

        try:
            # Base64 디코딩
            data = base64.b64decode(encrypted_data.encode("utf-8"))

            # nonce와 ciphertext 분리
            nonce = data[:12]
            ciphertext = data[12:]

            # 복호화
            plaintext_bytes = self.cipher.decrypt(nonce, ciphertext, None)
            return plaintext_bytes.decode("utf-8")

        except Exception as e:
            raise ValueError(f"복호화 실패: {str(e)}")

    def encrypt_dict(self, data: dict, fields_to_encrypt: list[str]) -> dict:
        """
        딕셔너리의 특정 필드들을 암호화

        Args:
            data: 원본 딕셔너리
            fields_to_encrypt: 암호화할 필드 목록

        Returns:
            암호화된 딕셔너리
        """
        encrypted_data = data.copy()

        for field in fields_to_encrypt:
            if field in encrypted_data and encrypted_data[field] is not None:
                encrypted_data[field] = self.encrypt(str(encrypted_data[field]))

        return encrypted_data

    def decrypt_dict(self, data: dict, fields_to_decrypt: list[str]) -> dict:
        """
        딕셔너리의 특정 필드들을 복호화

        Args:
            data: 암호화된 딕셔너리
            fields_to_decrypt: 복호화할 필드 목록

        Returns:
            복호화된 딕셔너리
        """
        decrypted_data = data.copy()

        for field in fields_to_decrypt:
            if field in decrypted_data and decrypted_data[field] is not None:
                try:
                    decrypted_data[field] = self.decrypt(decrypted_data[field])
                except ValueError:
                    # 복호화 실패 시 원본 유지 (이미 평문일 수 있음)
                    pass

        return decrypted_data


# 전역 인스턴스 (싱글톤 패턴)
password_hasher = PasswordHasher()
data_encryptor = DataEncryption()


def hash_password(password: str) -> str:
    """
    비밀번호 해싱 (전역 함수)

    Args:
        password: 평문 비밀번호

    Returns:
        해싱된 비밀번호
    """
    return password_hasher.hash_password(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    비밀번호 검증 (전역 함수)

    Args:
        plain_password: 평문 비밀번호
        hashed_password: 해싱된 비밀번호

    Returns:
        검증 결과
    """
    return password_hasher.verify_password(plain_password, hashed_password)


def encrypt_data(plaintext: str) -> str:
    """
    데이터 암호화 (전역 함수)

    Args:
        plaintext: 평문 데이터

    Returns:
        암호화된 데이터
    """
    return data_encryptor.encrypt(plaintext)


def decrypt_data(encrypted_data: str) -> str:
    """
    데이터 복호화 (전역 함수)

    Args:
        encrypted_data: 암호화된 데이터

    Returns:
        복호화된 데이터
    """
    return data_encryptor.decrypt(encrypted_data)
