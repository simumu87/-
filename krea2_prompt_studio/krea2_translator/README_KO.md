# Krea2 Embedded Translator 1.0.0

외부 번역 API를 사용하지 않는 로컬 한국어→영어 번역 모듈입니다.

## 구조
- `translator.py`: 번역 엔진
- `data/core_ko_en.json`: 기본 핵심 어휘
- `data/domains_ko_en.json`: 일상/로맨스/의상/원단/환경/포즈/카메라·조명 어휘
- `data/patterns.json`: 문맥·관계 패턴
- `data/normalization.json`: 영어 문장 정리 규칙
- `../krea2_prompt_configs/user_dictionary.json`: 사용자 추가 번역

## 우선순위
사용자 사전 → 핵심 사전 → 분야별 사전 → 패턴 → 정규화

## 원칙
번역기는 장면을 새로 만들지 않습니다. 입력된 의미를 영어 표현으로 바꾸는 역할만 담당합니다. 좌우 방향, 고정값, LoRA 트리거, 따옴표 안의 텍스트는 보호됩니다.
