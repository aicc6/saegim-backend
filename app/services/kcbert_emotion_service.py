"""
KC-BERT 감정 분류 모델 서비스
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

logger = logging.getLogger(__name__)


class KCBERTEmotionService:
    """KC-BERT 기반 감정 분류 서비스"""

    _instance: Optional["KCBERTEmotionService"] = None
    _model = None
    _tokenizer = None
    _label_mapping: Dict[int, str] = {}

    def __new__(cls) -> "KCBERTEmotionService":
        """싱글톤 패턴으로 모델 로딩 최적화"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """KC-BERT 모델 초기화"""
        if self._model is None:
            self._load_model()

    def _load_model(self):
        """KC-BERT 모델과 토크나이저 로드"""
        try:
            # 허깅페이스 모델 경로 설정
            model_path = "sl-seongjunlee/saegim-kcbert"
            
            logger.info(f"KC-BERT 모델 로딩 시작 (허깅페이스): {model_path}")

            # 기본 라벨 매핑 (허깅페이스 모델용)
            self._label_mapping = {
                0: "기쁨",
                1: "슬픔",
                2: "분노", 
                3: "평온",
                4: "불안"
            }
            logger.info(f"허깅페이스 모델용 라벨 매핑 사용: {self._label_mapping}")

            # 토크나이저 로드
            self._tokenizer = AutoTokenizer.from_pretrained(model_path)
            logger.info("KC-BERT 토크나이저 로드 완료")

            # 모델 로드
            self._model = AutoModelForSequenceClassification.from_pretrained(model_path)
            
            # GPU 사용 가능시 GPU로 이동
            if torch.cuda.is_available():
                self._model = self._model.cuda()
                logger.info("KC-BERT 모델을 GPU로 이동")
            else:
                logger.info("KC-BERT 모델을 CPU에서 실행")

            # 모델을 평가 모드로 설정
            self._model.eval()
            
            logger.info("KC-BERT 모델 로딩 완료")

        except Exception as e:
            logger.error(f"KC-BERT 모델 로딩 실패: {str(e)}")
            logger.warning("KC-BERT 모델 없이 실행됩니다. LLM 감정 분석을 사용합니다.")
            self._model = None
            self._tokenizer = None

    def is_available(self) -> bool:
        """KC-BERT 모델이 사용 가능한지 확인"""
        return self._model is not None and self._tokenizer is not None

    def predict_emotion(self, text: str) -> Tuple[str, float]:
        """
        텍스트에서 감정을 분류합니다.
        
        Args:
            text: 분석할 텍스트
            
        Returns:
            (감정_라벨, 신뢰도) 튜플
        """
        if not self.is_available():
            logger.warning("KC-BERT 모델이 로드되지 않았습니다")
            return "평온", 0.0

        if not text or not text.strip():
            logger.warning("빈 텍스트가 전달되었습니다")
            return "평온", 0.0

        try:
            # 텍스트 전처리 및 토크나이징
            inputs = self._tokenizer(
                text.strip(),
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512
            )

            # GPU 사용시 입력도 GPU로 이동
            if torch.cuda.is_available() and self._model.device.type == "cuda":
                inputs = {k: v.cuda() for k, v in inputs.items()}

            # 추론 실행
            with torch.no_grad():
                outputs = self._model(**inputs)
                logits = outputs.logits

            # 소프트맥스를 통해 확률 계산
            probabilities = torch.nn.functional.softmax(logits, dim=-1)
            
            # 가장 높은 확률의 클래스 선택
            predicted_class_id = probabilities.argmax().item()
            confidence = probabilities.max().item()

            # 라벨 매핑을 통해 감정 라벨 획득
            emotion_label = self._label_mapping.get(predicted_class_id, "평온")

            # 한글 라벨을 영어로 변환 (기존 시스템과 호환성)
            emotion_english = self._convert_to_english_emotion(emotion_label)

            logger.info(
                f"KC-BERT 감정 분석 완료: "
                f"텍스트='{text[:50]}...', "
                f"감정={emotion_label}({emotion_english}), "
                f"신뢰도={confidence:.3f}"
            )

            return emotion_english, confidence

        except Exception as e:
            logger.error(f"KC-BERT 감정 분석 실패: {str(e)}")
            return "평온", 0.0

    def _convert_to_english_emotion(self, korean_emotion: str) -> str:
        """한글 감정을 영어 감정으로 변환"""
        emotion_mapping = {
            "기쁨": "happy",
            "행복": "happy",
            "즐거움": "happy",
            "슬픔": "sad", 
            "우울": "sad",
            "분노": "angry",
            "화남": "angry",
            "짜증": "angry",
            "평온": "peaceful",
            "안정": "peaceful",
            "고요": "peaceful",
            "불안": "unrest",
            "걱정": "unrest",
            "초조": "unrest"
        }
        
        return emotion_mapping.get(korean_emotion, "peaceful")

    def batch_predict_emotions(self, texts: list[str]) -> list[Tuple[str, float]]:
        """
        여러 텍스트에 대해 배치 감정 분석 수행
        
        Args:
            texts: 분석할 텍스트 리스트
            
        Returns:
            (감정_라벨, 신뢰도) 튜플의 리스트
        """
        if not self.is_available():
            logger.warning("KC-BERT 모델이 로드되지 않았습니다")
            return [("peaceful", 0.0) for _ in texts]

        if not texts:
            return []

        try:
            # 배치 토크나이징
            inputs = self._tokenizer(
                texts,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512
            )

            # GPU 사용시 입력도 GPU로 이동
            if torch.cuda.is_available() and self._model.device.type == "cuda":
                inputs = {k: v.cuda() for k, v in inputs.items()}

            # 배치 추론 실행
            with torch.no_grad():
                outputs = self._model(**inputs)
                logits = outputs.logits

            # 소프트맥스를 통해 확률 계산
            probabilities = torch.nn.functional.softmax(logits, dim=-1)
            
            results = []
            for i in range(len(texts)):
                predicted_class_id = probabilities[i].argmax().item()
                confidence = probabilities[i].max().item()
                
                emotion_label = self._label_mapping.get(predicted_class_id, "평온")
                emotion_english = self._convert_to_english_emotion(emotion_label)
                
                results.append((emotion_english, confidence))

            logger.info(f"KC-BERT 배치 감정 분석 완료: {len(texts)}개 텍스트")
            return results

        except Exception as e:
            logger.error(f"KC-BERT 배치 감정 분석 실패: {str(e)}")
            return [("peaceful", 0.0) for _ in texts]


# 전역 인스턴스 (싱글톤)
kcbert_service = KCBERTEmotionService()


def get_kcbert_service() -> KCBERTEmotionService:
    """KC-BERT 서비스 인스턴스 반환"""
    return kcbert_service