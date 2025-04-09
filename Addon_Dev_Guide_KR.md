
# 월드 오브 워크래프트 애드온 제작 및 위크오라 개발 기준

## 🧾 기본 정보

- **제작자 닉네임 (인게임)**: `시무룩하다 야`
- **WoW 클라이언트 파일 버전**: `11.1.0.60189`
- **WoW 제품 버전**: `11.1.0`
- **기준 언어**: 한국어 클라이언트 (와우헤드 한국어판 기준)

---

## 🧰 애드온 제작 기준

1. **한국어 완전 대응**
   - 모든 게임 용어 및 고유명사는 [와우헤드 한국어 페이지](https://ko.wowhead.com)를 기준으로 번역
   - 클라이언트 언어 기준: 한국어

2. **패키지형 애드온(예: ElvUI)의 클론 제작**
   - 독립형으로 재구성하여 의존성을 없앰
   - 필요 시 ElvUI 내부 이미지 리소스를 활용

3. **일관성 있는 구조**
   - 파일 및 폴더 구성은 기능별로 명확하게 분리
   - 설정창 및 내부 코드 일체화
   - 향후 기능 확장 또는 다른 애드온과 통합을 고려한 설계

4. **유저 친화적 UI**
   - 설정창 제공 (Ace3 기반 또는 ElvUI 스타일)
   - 드래그 가능 위치 조절, 체크박스 옵션 등 기본 제공
   - 마우스오버 툴팁 표시, 바 이름 등 직관적인 시각 요소 활용

---

## ✨ WeakAura 제작 기준

1. **UI 구성**
   - 아이콘 + 타이머 바 형태
   - 시각적으로 깔끔하고 ElvUI 스타일 지향
   - 프레임 위치 조정 가능, 이름 라벨 및 색상 통일

2. **추적 대상 예시**
   - 예: 흑마법사의 울부짖는 불길, 박멸, 생명석, 악마 폭군 등
   - 파티 상태, 버프/디버프 유지 여부, 내부 쿨다운 추적 등 포함

3. **버전**
   - WeakAuras 애드온 버전: `5.19.7`
   - 한국어 클라이언트에서 정상 작동 기준

4. **설정 항목 정렬 기준**
   - 상단 좌측부터 → 디스플레이, 활성 조건, 조건, 동작, 애니메이션
   - 하단 좌측부터 → 불러오기, 사용자 정의 옵션, 정보

---

## 🔗 애드온/위크오라 제작 참고 자료

| 카테고리 | 설명 | 링크 |
|----------|------|------|
| 🔧 WoW API 문서 | Lua 기반 API 문서 | [wowpedia - API](https://wowpedia.fandom.com/wiki/World_of_Warcraft_API) |
| 📚 UI 프레임 문서 | XML 기반 UI 구성 문서 | [wowpedia - Frame](https://wowpedia.fandom.com/wiki/UIOBJECT_Frame) |
| 📘 TOC 문서 | AddOn 파일 구조 정의 | [wowpedia - TOC](https://wowpedia.fandom.com/wiki/TOC_format) |
| 🌐 와우헤드 한국어 | 모든 게임 용어 기준 | [와우헤드 (한국어)](https://ko.wowhead.com) |
| 🧰 WeakAura 공식 문서 | 트리거/조건 문법 등 | [WA 위키](https://github.com/WeakAuras/WeakAuras2/wiki) |
| 💬 UI 커뮤니티 | AddOn 개발자 포럼 | [WoWInterface](https://www.wowinterface.com/) |
| 📦 CurseForge | AddOn 배포 | [CurseForge](https://www.curseforge.com/wow/addons) |
| ⚙️ ElvUI GitHub | 소스 참고용 | [ElvUI GitHub](https://github.com/tukui-org/ElvUI) |
