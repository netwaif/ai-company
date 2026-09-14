# ai-company

AI 회사 생성기 — 총괄 봇 하나와 기존 폴더 봇들을 부서·직원으로 묶어, 요청 한 번으로 사슬 업무(기획 → 제작 → 검증)가 돌게 한다.
agentlayer의 배관(`send`·`task`·훅 자동 보고)과 folder-bot(봇·스레드) 위에서 동작한다.

## 설치

```
brew install netwaif/tap/agentlayer && agentlayer init        # 있으면 brew upgrade 뒤 init
/plugin marketplace add netwaif/folder-bot
/plugin install folder-bot@folder-bot
/plugin marketplace add netwaif/ai-company
/plugin install ai-company@ai-company
```

## 사용

```
AI 회사 만들어줘
```

스킬(configure-company)이 전 과정을 이끈다 — 회사 루트·부서·직원(기존 봇 / 새 폴더 / 호출형)을 묻고, 결정적 엔진 `companyctl`이
폴더·템플릿·총괄 절차·직원 지침 블록을 멱등 설치한다. 수동은 총괄 봇의 디스코드 포탈 단계뿐(folder-bot의 configure-bot이 안내).

**총괄 역할은 Claude Code 전용**(Monitor·SendMessage 의존). 직원은 Claude·Codex·Gemini(agy) 봇 모두 가능. 맥·리눅스·WSL2.

## 구조

```
<회사 루트>/                 = 총괄 봇 폴더
├─ CLAUDE.md                공동 규칙 + 총괄 절차(마커 블록)
├─ SESSION.md               세션 이어가기(없을 때만 생성)
├─ 직원명부.json             정본
├─ 업무요청/ 참고자료/ 결과물/ docs/ tasks/<업무ID>/ _templates/
└─ runtime/inbox/{pending,received,quarantine}/   총괄 수신함(agentlayer 훅이 씀)
```

직원 폴더에는 소속 부서 마커 블록 한 개만 추가된다. 보고 명령은 없다 — 직원의 상태 전이(끝남·승인 대기·오류)가 곧 보고다.

## 명령 (스킬이 대신 실행)

```bash
companyctl.py init --root ~/ai-folder/company --name "AI 회사"
companyctl.py employee add --root … --dept 비즈니스운영팀 --name "사업운영 매니저" --bot collab
companyctl.py install|doctor|remove|list --root …
```

## 비파괴 보장
SESSION.md는 없을 때만 만든다. 지침 파일은 마커 블록만 추가·제거(원문 복원). 토큰은 읽지도 쓰지도 않는다.

## 라이선스
MIT
