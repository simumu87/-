# v10.0.3 버그 수정

기준: v10.0.2 점검 결과(`docs/본체_점검결과_v10.0.2_20261004.md`)의 A 항목.
2인/1인 각 1,000시드(2,000건) 생성에서 실패 0건, 자가진단 통과를 확인했다.

수정:
- 창문/문이 한 글자씩 쪼개져 출력되던 문제 (`environment_prompt`)
- 단독 장면에 `looking toward the other person`이 나오던 문제
- 단독 장면에 2인용 포즈(서로 마주 보기, 나란히 앉기 등)가 선택되던 문제 (`PAIR_ONLY_POSES`)
- 공간 배치 문장 문법 (`foreground at in the far background` 등), 층별 위치 목록 분리
- 소품(케이블, 스마트폰 등)이 Background로 분류되던 문제 → 가구와 같은 Midground
- 포즈 목록의 존재하지 않는 키(`마주 앉아 대화`)로 생성이 실패하던 문제 (전체의 약 1.7%)
- 활동 18종에 영어 문구가 없어 한글이 프롬프트에 새던 문제 (`글쓰기`, `가볍게 포옹하기` 등)
- LoRA 미지정 시 `auto`가 트리거로 출력되던 문제 (`slot_trigger`)
- 문장 끝 마침표 누락 및 환경 스케일 규칙 문장 이어붙임
- f-string 안 백슬래시를 제거해 Python 3.12 미만에서도 문법 오류가 나지 않음

변경 없음: LoRA 트리거 맨 앞 출력, LoRA identity 고정, 프롬프트 구성 형식(다음 단계에서 개편).

회귀 테스트: `python tests/regression_bulk.py 300`
