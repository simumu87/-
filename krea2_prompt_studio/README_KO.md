# Krea2 Turbo Prompt Studio v10.0.2

Korean UI 기반의 Krea2 Turbo 자연어 영어 프롬프트 생성기입니다.

## 번역 모듈
`krea2_translator/`는 본체와 분리된 오프라인 한국어→영어 번역 모듈입니다.

우선순위:
사용자 사전 → 핵심 사전 → 분야별 사전 → 문장 패턴 → 영어 정리 규칙

번역 사전 업데이트는 다음 파일만 교체하면 됩니다.
- `krea2_translator/data/core_ko_en.json`
- `krea2_translator/data/domains_ko_en.json`
- `krea2_translator/data/patterns.json`
- `krea2_translator/data/normalization.json`

사용자 추가 사전은 본체 실행 폴더의 `krea2_prompt_configs/user_dictionary.json`에 저장됩니다.
외부 API, 인터넷 연결, 별도 유료 번역 서비스는 필요하지 않습니다.

## 실행
```text
python krea2_prompt_studio.py
```

번역 모듈 자체 테스트:
```text
python -m krea2_translator --self-test
python -m krea2_translator --stats
```

## 이번 버전의 검증 규칙
- 등록된 LoRA가 있으면 `loras.json`의 `identity`를 캐릭터 고정값으로 사용합니다. 미지정 상태에서 눈/머리/체형/특징을 새로 랜덤 생성하지 않습니다.
- LoRA 트리거는 최종 프롬프트의 첫 토큰으로 출력됩니다.
- 선택/해결된 테마, 행동, 공간, 의상, 원단, 환경, 조명, 카메라, 리얼리즘 등의 실제 값이 최종 프롬프트에 들어갔는지 자동 검사합니다.
- 최종 프롬프트는 한국어 누출, 반복 구두점, 잘못된 LoRA 지시문, 주요 구조 누락을 검사합니다.
- 사용 중인 `loras.json`은 패키지에 포함하지 않으며 기존 관리 파일을 그대로 참조합니다.
