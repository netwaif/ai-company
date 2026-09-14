---
name: configure-company
description: Use when the user wants to build or operate an "AI company" on top of their folder bots — create the company root, register departments and employees (existing folder-bot bots, new folders, or on-demand), install the manager (총괄) procedure, check or remove it. Triggers on "AI 회사 만들어줘", "회사에 직원 추가해줘", "부서 추가", "회사 점검해줘", "회사 제거해줘", "/configure-company". 결정적 엔진(companyctl.py)이 직원명부.json 정본으로 폴더·템플릿·지침 블록을 멱등 설치하고, 수동은 총괄 봇의 디스코드 포탈 단계뿐(folder-bot configure-bot에 위임).
---

# configure-company — AI 회사 생성기

총괄 봇 하나와 기존 폴더 봇들을 부서·직원으로 묶는다. 모든 파일 조작은 `generator/companyctl.py`가 한다 —
직접 명부·지침 파일을 손으로 쓰지 말 것. **비파괴 원칙**: SESSION.md는 없을 때만 만들고 있으면 절대 수정하지 않는다.
지침 파일은 마커 블록(`<!-- store:ai-company:start/end -->`)만 추가·제거한다. 토큰은 읽지도 쓰지도 않는다.

총괄 역할은 Claude Code 전용이다(Monitor·SendMessage 의존). 직원은 Claude·Codex·Gemini(agy) 봇 모두 가능.

## 회사 만들기

### 1. 전제 점검
```bash
python3 "<이 스킬 폴더>/generator/companyctl.py" doctor --root <회사 루트>   # 명부가 없으면 아래 init 뒤에 다시
```
- agentlayer ≥ 1.5.0(`agentlayer version`). 없거나 낮으면: `brew install netwaif/tap/agentlayer && agentlayer init`(리눅스: README의 install.sh). 그 뒤 반드시 `agentlayer init`.
- folder-bot 플러그인(`bot-thread`·`bot-up`가 `~/.local/bin`에 있음). 없으면 `/plugin marketplace add netwaif/folder-bot` → `/plugin install folder-bot` 안내 후 중단.
- tmux.

### 2. 질문 (AskUserQuestion 한 번에)
- 회사 루트(기본 `~/ai-folder/company`)
- 회사 이름(기본 "AI 회사")
- 부서 목록(기본 9부서 — 경영기획실·콘텐츠전략팀·기술개발팀·크리에이티브팀·기술검증팀·교육자료팀·채널그로스팀·커뮤니티·멤버십팀·비즈니스운영팀; 빼거나 추가 가능)
AskUserQuestion이 없는 환경에서는 채팅으로 같은 질문을 하고 답을 받는다. 기본값으로 질주하지 말 것.

### 3. 회사 루트 생성
```bash
python3 "<이 스킬 폴더>/generator/companyctl.py" init --root <루트> --name "<이름>" [--depts a,b,c]
```

### 4. 직원 등록 (부서마다 한 번씩 물어본다)
먼저 `python3 - <<'EOF'` 없이 `cat ~/.config/folder-bot/bots.json`으로 기존 봇 이름·폴더를 읽어 표로 보여 준다(토큰 없음, 읽어도 됨). 부서마다 세 가지 중 하나를 고르게 한다:
- **기존 봇**: `companyctl employee add --root <루트> --dept <부서> --name <직원명> --bot <bots.json 이름>` — 채널 ID는 그 봇 폴더의 `.discord-state/access.json`에서 자동으로 읽는다(둘 이상이면 `--channel-id`).
- **새 폴더 + 새 봇**: `companyctl employee add ... --folder <새 폴더> --engine claude|codex|agy` → 그 폴더에서 folder-bot의 **configure-bot** 스킬로 봇을 만든 뒤(포탈 수동 단계 포함) `companyctl employee add ... --bot <새 봇 이름> --replace`로 갱신.
- **호출형**: `companyctl employee add ... --on-demand` — 폴더·봇 없음, 총괄이 필요할 때 `claude -p`로 처리.
경영기획실(총괄)은 직원으로 등록하지 않는다 — 회사 루트 자체가 총괄 봇 폴더다.

### 5. 설치
```bash
python3 "<이 스킬 폴더>/generator/companyctl.py" install --root <루트>
```
출력을 그대로 보여 준다(템플릿·SESSION.md·총괄 블록·직원 블록).

### 6. 총괄 봇 (수동 단계 포함)
회사 루트에서 folder-bot의 **configure-bot** 스킬을 실행한다("이 폴더를 디스코드 봇으로 만들어줘", 봇 이름 예: `company`, 세션 `company-bot`). 디스코드 포탈·토큰·초대·페어링은 그 스킬의 안내를 따른다. 직원 채널들은 한 카테고리에 모아 두는 것을 권한다(채널 ID는 바뀌지 않으므로 이동은 자유).

### 7. 검증
```bash
python3 "<이 스킬 폴더>/generator/companyctl.py" doctor --root <루트>
```
FAIL이 없으면 무해한 사슬 한 번: 총괄 채널(또는 회사 루트의 claude 세션)에서 "직원 <이름>에게 '도구 없이 OK라고만 답해'를 업무 LAB-1로 보내고 보고를 기다려 줘". 총괄 절차대로 스레드 생성 → `task assign` → `send` → Monitor 이벤트 `to: DONE_UNREAD`가 오면 성공. 결과를 사용자에게 그대로 보여 준다.

## 직원 추가·제거 / 부서 추가·제거
`companyctl employee add|remove`, `companyctl dept add|remove` 뒤 반드시 `companyctl install`(블록 갱신). 직원 제거는 명부에서만 빼며 그 폴더의 블록은 `install`이 다시 돌 때 유지된다 — 블록까지 걷으려면 먼저 `companyctl remove`, 명부 수정, `install`.

## 점검
`companyctl doctor --root <루트>` — 읽기 전용. agentlayer 버전·도구·명부·총괄 블록·수신함·직원별 폴더/블록/등록/채널·낡은 업무(`stale`·`gone`)·활성 업무 수.

## 제거
`companyctl remove --root <루트>` — 총괄·직원 지침 블록만 걷어낸다. 직원명부·SESSION.md·업무요청·결과물·tasks·runtime은 보존(삭제는 사용자 몫). 총괄 봇 자체는 folder-bot의 제거 절차.
