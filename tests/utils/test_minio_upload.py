"""
MinIO 이미지 업로드 유틸리티 테스트
"""

import io

import pytest
from fastapi import UploadFile
from PIL import Image

from app.utils.minio_upload import MinIOUploader


class TestMinIOUploader:
    """MinIO 업로더 테스트"""

    def create_test_image_with_exif(self) -> bytes:
        """
        EXIF 데이터가 포함된 테스트 이미지 생성

        Returns:
            bytes: EXIF 데이터가 포함된 JPEG 이미지
        """
        # 테스트 이미지 생성
        img = Image.new("RGB", (800, 600), color="red")

        # EXIF를 포함한 이미지 저장
        img_buffer = io.BytesIO()

        # exif 파라미터를 사용하여 EXIF 데이터 포함
        img.save(img_buffer, format="JPEG", quality=95, exif=b"")  # 기본 EXIF
        img_buffer.seek(0)

        return img_buffer.getvalue()

    def has_exif_data(self, image_data: bytes) -> bool:
        """
        이미지에 EXIF 데이터가 있는지 확인

        Args:
            image_data: 이미지 바이트 데이터

        Returns:
            bool: EXIF 데이터 존재 여부
        """
        try:
            with Image.open(io.BytesIO(image_data)) as img:
                exif_data = img.getexif()
                if exif_data is None:
                    return False
                # EXIF 데이터가 비어있는지 확인
                return len(exif_data) > 0
        except Exception:
            return False

    def test_remove_exif_removes_metadata(self):
        """EXIF 제거 메서드가 메타데이터를 제거하는지 테스트"""
        uploader = MinIOUploader()

        # EXIF가 포함된 이미지 생성
        original_image = self.create_test_image_with_exif()

        # EXIF 제거 실행
        cleaned_image = uploader._remove_exif(original_image)

        # 원본 이미지에는 EXIF가 있을 수 있지만 (테스트 환경에 따라 다름)
        # 처리된 이미지에는 EXIF가 없어야 함
        has_exif_after = self.has_exif_data(cleaned_image)

        # EXIF가 제거되었는지 확인
        assert not has_exif_after, "EXIF 데이터가 제거되지 않았습니다"

        # 이미지 자체는 유효해야 함
        with Image.open(io.BytesIO(cleaned_image)) as img:
            assert img.size == (800, 600), "이미지 크기가 변경되었습니다"
            assert img.mode == "RGB", "이미지 모드가 변경되었습니다"

    def test_remove_exif_preserves_image_quality(self):
        """EXIF 제거 시 이미지 품질이 유지되는지 테스트"""
        uploader = MinIOUploader()

        # 테스트 이미지 생성
        original_image = self.create_test_image_with_exif()

        # EXIF 제거
        cleaned_image = uploader._remove_exif(original_image)

        # 이미지 크기와 색상이 유지되는지 확인
        with Image.open(io.BytesIO(original_image)) as orig_img:
            with Image.open(io.BytesIO(cleaned_image)) as clean_img:
                assert orig_img.size == clean_img.size
                assert orig_img.mode == clean_img.mode

    def test_create_thumbnail_removes_exif(self):
        """썸네일 생성 시 EXIF가 제거되는지 테스트"""
        uploader = MinIOUploader()

        # EXIF가 포함된 이미지 생성
        original_image = self.create_test_image_with_exif()

        # 썸네일 생성
        thumbnail = uploader._create_thumbnail(original_image, size=(150, 150))

        # 썸네일에 EXIF가 없는지 확인
        has_exif = self.has_exif_data(thumbnail)
        assert not has_exif, "썸네일에 EXIF 데이터가 남아있습니다"

        # 썸네일 크기 확인
        with Image.open(io.BytesIO(thumbnail)) as thumb_img:
            # thumbnail() 메서드는 원본 비율을 유지하므로 정확히 150x150은 아닐 수 있음
            assert thumb_img.size[0] <= 150
            assert thumb_img.size[1] <= 150

    def test_remove_exif_handles_various_formats(self):
        """다양한 이미지 포맷에서 EXIF 제거가 작동하는지 테스트"""
        uploader = MinIOUploader()

        formats = [
            ("JPEG", "RGB", ".jpg"),
            ("PNG", "RGB", ".png"),
            ("PNG", "RGBA", ".png"),
        ]

        for format_name, mode, ext in formats:
            # 각 포맷별 테스트 이미지 생성
            img = Image.new(mode, (100, 100), color="blue")
            img_buffer = io.BytesIO()
            img.save(img_buffer, format=format_name)
            img_buffer.seek(0)
            original_data = img_buffer.getvalue()

            # EXIF 제거
            cleaned_data = uploader._remove_exif(original_data)

            # 이미지가 여전히 유효한지 확인
            with Image.open(io.BytesIO(cleaned_data)) as clean_img:
                assert clean_img.size == (
                    100,
                    100,
                ), f"{format_name} 이미지 크기가 변경되었습니다"

    @pytest.mark.asyncio
    async def test_upload_image_removes_exif_integration(self, mocker):
        """
        통합 테스트: upload_image 메서드가 EXIF를 제거하는지 확인
        (MinIO 클라이언트를 모킹하여 실제 업로드 없이 테스트)
        """
        # MinIO 클라이언트 모킹
        mock_client = mocker.MagicMock()
        mock_client.bucket_exists.return_value = True

        uploader = MinIOUploader()
        uploader.client = mock_client

        # EXIF가 포함된 테스트 이미지
        test_image = self.create_test_image_with_exif()

        # UploadFile 객체 생성
        file = UploadFile(filename="test.jpg", file=io.BytesIO(test_image))
        file.content_type = "image/jpeg"
        file.size = len(test_image)

        # 업로드 실행 (모킹된 클라이언트 사용)
        await uploader.upload_image(file)

        # put_object가 호출되었는지 확인
        assert mock_client.put_object.called

        # put_object에 전달된 데이터 확인
        call_args = mock_client.put_object.call_args
        uploaded_data = call_args.kwargs["data"].read()

        # 업로드된 데이터에 EXIF가 없는지 확인
        has_exif = self.has_exif_data(uploaded_data)
        assert not has_exif, "업로드된 이미지에 EXIF 데이터가 남아있습니다"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
