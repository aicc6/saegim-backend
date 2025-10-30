"""
KC-BERT 감정 분류 테스트 스크립트

독립적으로 KC-BERT 모델을 로드하고 감정을 추론하는 테스트용 파일입니다.
API와 별개로 모델의 동작을 확인할 수 있습니다.

사용법:
    python test_kcbert.py
    또는
    from test_kcbert import predict_emotion_with_confidence
    result = predict_emotion_with_confidence("오늘 정말 기분이 좋아요!")
"""

import json
import os
import sys
from typing import Dict, Optional, Tuple
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KCBERTEmotionPredictor:
    """KC-BERT 감정 분류 예측기"""
    
    def __init__(self, model_path: str = "sl-seongjunlee/saegim-kcbert"):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.label_mapping = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 모델 자동 로드
        self.load_model()
        
    def load_model(self) -> bool:
        """모델과 토크나이저를 로드합니다."""
        try:
            logger.info(f"KC-BERT 모델 로딩 시작... (경로: {self.model_path})")
            
            # 허깅페이스 모델인지 로컬 모델인지 확인
            is_huggingface_model = not os.path.exists(self.model_path)
            
            if not is_huggingface_model:
                # 로컬 모델인 경우 기존 로직
                label_mapping_path = os.path.join(self.model_path, "label_mapping.json")
                if (os.path.exists(label_mapping_path)):
                    with open(label_mapping_path, 'r', encoding='utf-8') as f:
                        label_data = json.load(f)
                        # id2label 형식으로 변환
                        if "id2label" in label_data:
                            self.label_mapping = label_data["id2label"]
                        else:
                            self.label_mapping = label_data
                    logger.info(f"✅ 라벨 매핑 로드 완료: {self.label_mapping}")
                else:
                    # 기본 감정 라벨 (한국어) - 5가지
                    self.label_mapping = {
                        "0": "기쁨",
                        "1": "슬픔", 
                        "2": "분노",
                        "3": "평온",
                        "4": "불안"
                    }
                    logger.warning("⚠️ label_mapping.json을 찾을 수 없어 기본 매핑을 사용합니다.")
            else:
                # 허깅페이스 모델인 경우 기본 매핑 사용
                self.label_mapping = {
                    "0": "기쁨",
                    "1": "슬픔", 
                    "2": "분노",
                    "3": "평온",
                    "4": "불안"
                }
                logger.info(f"✅ 허깅페이스 모델용 기본 라벨 매핑 사용: {self.label_mapping}")
            
            # 토크나이저 로드
            logger.info("토크나이저 로딩 중...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            logger.info("✅ 토크나이저 로드 완료")
            
            # 모델 로드
            logger.info("모델 로딩 중...")
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"✅ 모델 로드 완료 (디바이스: {self.device})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ KC-BERT 모델 로딩 실패: {str(e)}")
            return False
    
    def predict_emotion(self, text: str) -> Tuple[Optional[str], Optional[float]]:
        """
        텍스트에서 감정을 예측합니다.
        
        Args:
            text (str): 분석할 텍스트
            
        Returns:
            Tuple[Optional[str], Optional[float]]: (예측된 감정 라벨, 신뢰도)
        """
        try:
            if self.model is None or self.tokenizer is None:
                logger.error("❌ 모델 또는 토크나이저가 로드되지 않았습니다.")
                return None, None
            
            if not text.strip():
                logger.warning("⚠️ 빈 텍스트가 입력되었습니다.")
                return None, None
            
            logger.info(f"🔍 감정 분석 시작: '{text[:50]}...'")
            
            # 텍스트 전처리 및 토크나이징
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512
            )
            
            # GPU로 입력 데이터 이동
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            
            # 예측 수행
            with torch.no_grad():
                outputs = self.model(**inputs)
                probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)
                predicted_class_id = probabilities.argmax().item()
                confidence = probabilities.max().item()
            
            # 라벨 매핑을 통해 감정 문자열 반환
            emotion = self.label_mapping.get(str(predicted_class_id), "알 수 없음")
            
            logger.info(f"✅ 예측 완료: {emotion} (신뢰도: {confidence:.3f})")
            return emotion, confidence
            
        except Exception as e:
            logger.error(f"❌ 감정 예측 실패: {str(e)}")
            return None, None
    
    def is_model_loaded(self) -> bool:
        """모델이 로드되었는지 확인합니다."""
        return self.model is not None and self.tokenizer is not None

# 전역 예측기 인스턴스
predictor = None

def initialize_predictor(model_path: str = "sl-seongjunlee/saegim-kcbert") -> bool:
    """예측기를 초기화합니다."""
    global predictor
    try:
        predictor = KCBERTEmotionPredictor(model_path)
        return predictor.is_model_loaded()
    except Exception as e:
        logger.error(f"❌ 예측기 초기화 실패: {str(e)}")
        return False

def predict_emotion_with_confidence(text: str, model_path: str = "sl-seongjunlee/saegim-kcbert") -> Dict[str, any]:
    """
    텍스트에서 감정과 신뢰도를 예측하는 메인 함수
    
    Args:
        text (str): 분석할 텍스트
        model_path (str): 모델 경로
        
    Returns:
        Dict[str, any]: {
            'emotion': str,      # 예측된 감정
            'confidence': float, # 신뢰도 (0.0 ~ 1.0)
            'success': bool,     # 성공 여부
            'error': str         # 오류 메시지 (실패 시)
        }
    """
    global predictor
    
    logger.info(f"🔥 KC-BERT 함수 호출 시작 - 입력 텍스트: '{text[:50]}...' (길이: {len(text)})")
    
    # 예측기가 초기화되지 않았으면 초기화
    if predictor is None or not predictor.is_model_loaded():
        logger.info("🔄 예측기 초기화 중...")
        if not initialize_predictor(model_path):
            logger.error("❌ KC-BERT 함수 호출 실패: 모델 로딩 실패")
            return {
                'emotion': None,
                'confidence': None,
                'success': False,
                'error': '모델 로딩에 실패했습니다.'
            }
    
    # 감정 예측 수행
    logger.info("🎯 KC-BERT 감정 예측 수행 중...")
    emotion, confidence = predictor.predict_emotion(text)
    
    if emotion is not None and confidence is not None:
        logger.info(f"✅ KC-BERT 함수 호출 성공: {emotion} (신뢰도: {confidence:.3f})")
        return {
            'emotion': emotion,
            'confidence': confidence,
            'success': True,
            'error': None
        }
    else:
        logger.error("❌ KC-BERT 함수 호출 실패: 감정 예측 실패")
        return {
            'emotion': None,
            'confidence': None,
            'success': False,
            'error': '감정 예측에 실패했습니다.'
        }

def main():
    """메인 함수 - 대화형 테스트"""
    print("=" * 60)
    print("🤖 KC-BERT 감정 분류 테스트")
    print("=" * 60)
    
    # 예측기 초기화
    print("📥 모델 로딩 중...")
    if not initialize_predictor():
        print("❌ 모델 로딩에 실패했습니다. 프로그램을 종료합니다.")
        return
    
    print("✅ 모델 로딩 완료!")
    print("\n💡 사용법: 텍스트를 입력하면 감정을 분석합니다.")
    print("💡 종료하려면 'quit', 'exit', 또는 빈 문장을 입력하세요.\n")
    
    # 테스트 예시
    test_samples = [
        "오늘 정말 기분이 좋아요!",
        "너무 슬프고 우울해요...",
        "화가 나서 견딜 수 없어요!",
        "걱정이 많아서 잠이 안 와요.",
        "마음이 평온하고 차분해요."
    ]
    
    print("📝 테스트 예시:")
    for i, sample in enumerate(test_samples, 1):
        result = predict_emotion_with_confidence(sample)
        if result['success']:
            print(f"  {i}. '{sample}' → {result['emotion']} (신뢰도: {result['confidence']:.3f})")
        else:
            print(f"  {i}. '{sample}' → 실패: {result['error']}")
    
    print("\n" + "=" * 60)
    
    # 대화형 테스트
    while True:
        try:
            text = input("\n📝 분석할 텍스트를 입력하세요: ").strip()
            
            if not text or text.lower() in ['quit', 'exit', '종료']:
                print("👋 프로그램을 종료합니다.")
                break
            
            result = predict_emotion_with_confidence(text)
            
            if result['success']:
                print(f"🎯 결과: {result['emotion']} (신뢰도: {result['confidence']:.3f})")
            else:
                print(f"❌ 오류: {result['error']}")
                
        except KeyboardInterrupt:
            print("\n👋 프로그램을 종료합니다.")
            break
        except Exception as e:
            print(f"❌ 예상치 못한 오류: {str(e)}")

if __name__ == "__main__":
    main()