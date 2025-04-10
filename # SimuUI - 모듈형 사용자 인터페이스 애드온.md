# SimuUI - 모듈형 사용자 인터페이스 애드온

SimuUI는 ElvUI 스타일을 참고하여 제작된 **모듈형 WoW UI 애드온 프레임워크**입니다.  
초기 버전은 액션바 단축키 축약 기능과 빠른 주시(Focus) 기능을 포함하며, 계정 단위로 설정이 저장됩니다.

---

## 0단계 개발 계획

### 1. 기본 애드온 구조

- `SimuUI.toc`: 메타 정보와 파일 목록 정의
- `core.lua`: 모듈 로딩/이벤트 처리
- `config.lua`: 기본 설정값 및 초기화
- `SavedVariables`: `SimuUIDB` (계정 단위 저장)

---

### 2. SavedVariables 구조

```lua
SimuUIDB = {
    actionbar = {
        enabled = true,
        font = STANDARD_TEXT_FONT, -- 기본 클라이언트 폰트 사용 (한글 호환)
        size = 12,
        color = { r = 1, g = 1, b = 1 },
    },
    quickfocus = {
        enabled = true,
        modifier = "SHIFT",
        button = "BUTTON3", -- 마우스 가운데 버튼
    }
}

# SimuUI: 완전복제 기반 프레임워크 설계 계획

## 목적

SimuUI는 ElvUI의 모듈형 구조를 최대한 동일하게 복제하여,  
예측 가능한 기능 구현 및 안정적인 애드온 개발 기반을 제공하는 것을 목표로 합니다.

---

## 왜 완전복제를 선택했는가?

- 기존 방식은 반복적인 오류와 수정의 연속이었음
- ElvUI의 내부 구조를 정확히 이해하고 기능을 구현하는 데 한계 발생
- 기능 구현보다 구조 정리에 많은 리소스 소모
- 예상과 다른 처리 방식이 자주 등장함

**따라서, ElvUI의 구조를 완전히 복제하여 안정적이고 직관적인 개발 환경을 구축하기로 함**

---

## 복제 대상 (ElvUI 구조 기반)

### 1. Core 시스템

| 파일명 | 설명 |
|--------|------|
| Core.lua | 전역 네임스페이스 및 초기화 |
| Init.lua | 초기 이벤트 처리 및 Load 순서 |
| ModuleHandling.lua | 모듈 등록/초기화 (`RegisterModule`, `InitializeModule`) |
| ConfigHandling.lua | 설정값 저장 구조 처리 (`E.db`, `E.global`, `E.private`) |

> 네임스페이스는 `E` → `SimuUI` 또는 `SUI` 등으로 변경

---

### 2. 설정 저장 구조

ElvUI 방식의 설정 저장 시스템을 동일하게 구현:

```lua
SimuUI.db = {
  global = {},
  profile = {
    ActionBar = {},
    FocusAssist = {},
  },
  private = {},
}