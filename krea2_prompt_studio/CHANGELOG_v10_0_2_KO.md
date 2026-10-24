# v10.0.2 복구 내역

이번 버전은 LoRA Identity 누락을 복구한 패치입니다.

복구된 항목:
- LoRA 등록 데이터의 `identity` 저장 및 불러오기
- LoRA trigger로 등록 Identity 자동 조회
- 자연어/랜덤 생성에서 LoRA Identity 자동 연결
- 최종 인물 프롬프트의 `LoRA identity anchor` 문구
- LoRA가 인물의 WHO를 정의한다는 고정 규칙
- 얼굴 정체성, 얼굴 구조, 헤어 정체성, 고유 특징, 체형 비율, 피부톤 등의 유지 규칙
- Identity를 다른 인물과 교체/일반화/미화/연령변경/혼합하지 않도록 하는 고정 규칙
- LoRA 관리 UI에서 Identity 설명을 직접 등록/수정
- 장면 미리보기 및 메타데이터에 LoRA trigger/Identity 표시

원래 등록 파일에 Identity가 들어 있다면 기존 정보도 그대로 읽습니다.
