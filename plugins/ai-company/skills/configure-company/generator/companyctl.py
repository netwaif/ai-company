#!/usr/bin/env python3
"""companyctl — AI 회사 생성기의 결정적 엔진.
정본은 <root>/직원명부.json 하나. 지침 파일은 마커 블록만 추가·제거하고 SESSION.md는 없을 때만 만든다.
비밀값은 읽지도 쓰지도 않는다. 표준 라이브러리만 쓴다.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROSTER = "직원명부.json"
DEFAULT_DEPTS = ["경영기획실", "콘텐츠전략팀", "기술개발팀", "크리에이티브팀", "기술검증팀",
                 "교육자료팀", "채널그로스팀", "커뮤니티·멤버십팀", "비즈니스운영팀"]
COMPANY_DIRS = ["업무요청", "참고자료", "결과물", "docs", "tasks",
                "runtime/inbox/pending", "runtime/inbox/received", "runtime/inbox/quarantine"]

ASSETS = Path(__file__).resolve().parent.parent / "assets"
MARK_START = "<!-- store:ai-company:start -->"
MARK_END = "<!-- store:ai-company:end -->"
AGY_HEADER = "---\ntrigger: always_on\n---\n"
TEMPLATES = ["task.md", "업무요청.md", "log.md"]


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def roster_path(root: Path) -> Path:
    return root / ROSTER


def load_roster(root: Path) -> dict:
    p = roster_path(root)
    if not p.exists():
        die(f"직원명부가 없습니다: {p} — 먼저 `companyctl init --root {root}`")
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        die(f"직원명부 JSON 손상: {p}")
    r.setdefault("version", 1)
    r.setdefault("name", "AI 회사")
    r.setdefault("departments", [])
    r.setdefault("employees", [])
    if not isinstance(r["departments"], list) or not isinstance(r["employees"], list):
        die(f"직원명부 JSON 손상: {p}")
    for e in r["employees"]:
        if isinstance(e, dict):
            for k, dv in (("dept", ""), ("name", ""), ("tool", "claude"), ("mode", "on-demand"),
                          ("session", ""), ("folder", ""), ("bot", ""), ("channel_id", "")):
                e.setdefault(k, dv)
    return r


def save_roster(root: Path, r: dict) -> None:
    p = roster_path(root)
    tmp = p.with_name("." + p.name + ".tmp")
    tmp.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def cmd_init(a) -> None:
    root = Path(a.root).expanduser().resolve()
    for d in COMPANY_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    p = roster_path(root)
    if p.exists():
        r = load_roster(root)
        changed = False
        if a.name and r.get("name") != a.name:
            r["name"] = a.name
            changed = True
        if changed:
            save_roster(root, r)
        print(f"직원명부 유지: {p} (직원 {len(r['employees'])}명, 부서 {len(r['departments'])}개)")
        return
    if a.depts:
        seen = []
        for d in a.depts.split(","):
            d = d.strip()
            if d and d not in seen:
                seen.append(d)
        if not seen:
            die("--depts에 부서가 없습니다")
        depts = seen
    else:
        depts = list(DEFAULT_DEPTS)
    r = {"version": 1, "name": a.name or "AI 회사", "departments": depts, "employees": []}
    save_roster(root, r)
    print(f"직원명부 생성: {p} (부서 {len(depts)}개)")


def cmd_dept(a) -> None:
    root = Path(a.root).expanduser().resolve()
    r = load_roster(root)
    if a.action == "add":
        if a.name not in r["departments"]:
            r["departments"].append(a.name)
            save_roster(root, r)
        print(f"부서: {', '.join(r['departments'])}")
    else:
        if any(e["dept"] == a.name for e in r["employees"]):
            die(f"부서 {a.name}에 직원이 있습니다 — 먼저 employee remove")
        r["departments"] = [d for d in r["departments"] if d != a.name]
        save_roster(root, r)
        print(f"부서: {', '.join(r['departments'])}")


def cmd_list(a) -> None:
    root = Path(a.root).expanduser().resolve()
    r = load_roster(root)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(f"{r['name']} — {root}")
    for d in r["departments"]:
        emps = [e for e in r["employees"] if e["dept"] == d]
        if not emps:
            print(f"  {d}: (호출형/미배정)")
        for e in emps:
            where = e.get("session") or e.get("folder") or "-"
            print(f"  {d}: {e['name']} [{e['tool']}/{e['mode']}] {where}")


def bots_json_path() -> Path:
    return Path.home() / ".config" / "folder-bot" / "bots.json"


def read_bots() -> dict:
    p = bots_json_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        die(f"bots.json JSON 손상: {p}")


def channel_id_of(folder: Path) -> list:
    p = folder / ".discord-state" / "access.json"
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text(encoding="utf-8")).get("groups", {}).keys())
    except (ValueError, AttributeError):
        return []


def bridge_channel_id(bot_name: str, b: dict) -> tuple:
    """folder-bot --engine codex|agy 봇은 폴더에 .discord-state가 없다 — 채널은 브리지 인스턴스
    <bridge_dir>/.env.<봇>의 TUI_CHANNEL_ID. (경로, 채널 ID)를 돌려주고 파일이 없으면 ID는 ""."""
    p = Path(b.get("bridge_dir") or "~/codex-discord").expanduser() / f".env.{bot_name}"
    if not p.is_file():
        return p, ""
    return p, parse_env_file(p).get("TUI_CHANNEL_ID", "")


def manager_bot_of(root: Path) -> tuple:
    """bots.json에서 folder가 회사 루트와 같은 봇(총괄 봇) → (이름, 항목). 없으면 (None, None)."""
    for name, b in read_bots().items():
        f = b.get("folder")
        if f and Path(f).expanduser().resolve() == root:
            return name, b
    return None, None


def restart_manager_bot(root: Path) -> list:
    """회사 루트가 이미 폴더 봇이면 bot-restart <세션>으로 재시작한다 — 돌고 있던 봇은 방금 설치한
    총괄 블록을 읽지 않은 상태라서다. bot-restart는 tmux pane 교체(respawn)라 systemd 유닛·tmux 세션
    생성 시각은 그대로다(재시작 확인은 pane 안 프로세스·세션 ID로). 출력 줄 목록을 돌려준다."""
    name, b = manager_bot_of(root)
    if not b:
        return []
    sess = b.get("session") or f"{name}-bot"
    exe = str(Path.home() / ".local" / "bin" / "bot-restart")  # folder-bot이 설치하는 자리
    if not Path(exe).is_file():
        exe = shutil.which("bot-restart") or exe
    if not Path(exe).is_file():
        return [f"WARN 총괄 봇 {name}(세션 {sess})이 총괄 블록을 아직 못 읽었는데 bot-restart가 없어 재시작 못 함 — "
                f"folder-bot 플러그인을 갱신한 뒤 수동으로: bot-restart {sess}"]
    try:
        r = subprocess.run([exe, sess], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as ex:
        return [f"WARN 총괄 봇 재시작 실패({sess}): {ex} — 수동으로: bot-restart {sess}"]
    out = " ".join((r.stdout.strip() or r.stderr.strip()).splitlines())
    if r.returncode != 0:
        return [f"WARN 총괄 봇 재시작 실패({sess}, exit {r.returncode}): {out} — 수동으로: bot-restart {sess}"]
    return [f"총괄 봇 재시작: {sess}" + (f" — {out}" if out else "")]


def tool_of_engine(engine: str) -> str:
    return {"claude": "claude", "codex": "codex", "agy": "gemini", "gemini": "gemini"}.get(engine, engine)


def parse_env_file(path: Path) -> dict:
    """codex-discord 브리지 .env(KEY=VALUE, # 주석, 따옴표 허용)를 읽는다. 토큰 값은 쓰지 않고 버린다."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip().strip('"').strip("'")
        out[k] = v
    return {k: v for k, v in out.items() if not k.endswith("TOKEN")}


def apply_env_file(a) -> None:
    """--env-file <브리지 .env>: 세션(TUI_PANE)·채널(TUI_CHANNEL_ID)·폴더(CODEX_WORKDIR)·엔진(ENGINE)을
    채운다. 명시 인자가 우선. 라이브 TUI 모드가 아니면(TUI_PANE 없음) 직원이 될 수 없다 — 총괄이 보낼
    tmux pane이 없기 때문."""
    p = Path(a.env_file).expanduser()
    if not p.is_file():
        die(f"env 파일이 없습니다: {p}")
    env = parse_env_file(p)
    pane = env.get("TUI_PANE", "")
    if not a.session:
        if not pane:
            die(f"{p.name}에 TUI_PANE이 없습니다 — 헤드리스 브리지는 직원이 될 수 없습니다(총괄이 보낼 tmux pane 없음). "
                f"TUI_PANE(예: gemini-live:0.0)·TUI_CHANNEL_ID를 넣고 `bash scripts/install.sh`를 재실행(codex-discord v0.1.22+, 자동 기동 유닛)한 뒤 다시 하세요")
        a.session = pane.split(":", 1)[0]
    if not a.channel_id:
        a.channel_id = env.get("TUI_CHANNEL_ID", "")
    if not a.folder:
        a.folder = env.get("CODEX_WORKDIR", "")
        if not a.folder:
            die(f"{p.name}에 CODEX_WORKDIR이 없습니다 — --folder로 지정")
    if not a.engine:
        a.engine = env.get("ENGINE", "codex") or "codex"


def cmd_employee(a) -> None:
    root = Path(a.root).expanduser().resolve()
    r = load_roster(root)
    if a.action == "add" and getattr(a, "env_file", None):
        apply_env_file(a)
    if a.action == "add" and not getattr(a, "engine", None):
        a.engine = "claude"
    if a.action == "remove":
        before = len(r["employees"])
        r["employees"] = [e for e in r["employees"] if e["name"] != a.name]
        if len(r["employees"]) == before:
            die(f"직원 {a.name}이 명부에 없습니다")
        save_roster(root, r)
        print(f"직원 제거: {a.name}")
        return
    if not a.dept:
        die("--dept 필요")
    if a.dept not in r["departments"]:
        die(f"부서 {a.dept}이 명부에 없습니다 — `companyctl dept add --name {a.dept}` 먼저")
    if sum(map(bool, [a.bot, a.folder, a.on_demand])) != 1:
        die("--bot <이름> | --folder <폴더> | --on-demand 중 하나만 지정")
    exists = [e for e in r["employees"] if e["name"] == a.name]
    if exists and not a.replace:
        die(f"직원 {a.name}이 이미 있습니다 (--replace로 교체)")
    e = {"dept": a.dept, "name": a.name, "tool": "claude", "mode": "on-demand",
         "session": "", "folder": "", "bot": "", "channel_id": ""}
    if a.bot:
        bots = read_bots()
        if a.bot not in bots:
            die(f"folder-bot bots.json에 {a.bot} 봇이 없습니다: {bots_json_path()}")
        b = bots[a.bot]
        if not b.get("folder"):
            die(f"bots.json의 {a.bot} 봇에 folder가 없습니다: {bots_json_path()}")
        folder = Path(b["folder"]).expanduser().resolve()
        if folder == root:
            die("회사 루트는 직원으로 등록할 수 없습니다(총괄 폴더)")
        ids = channel_id_of(folder)
        cid = a.channel_id or (ids[0] if len(ids) == 1 else "")
        env_path = None
        if not cid and not ids and b.get("engine") in ("codex", "agy", "gemini"):
            env_path, cid = bridge_channel_id(a.bot, b)
        if not cid:
            hint = f"브리지 {env_path}에 TUI_CHANNEL_ID 없음" if env_path else f"access.json groups: {ids}"
            die(f"채널 ID를 정할 수 없습니다({hint}) — --channel-id <ID>로 지정")
        e.update(tool=tool_of_engine(b.get("engine", "claude")), mode="bot", session=b.get("session", ""),
                 folder=str(folder), bot=a.bot, channel_id=cid)
    elif a.folder:
        folder = Path(a.folder).expanduser().resolve()
        if folder == root:
            die("회사 루트는 직원으로 등록할 수 없습니다(총괄 폴더)")
        if a.session:
            # folder-bot 밖에서 도는 봇(LaunchAgent·codex-discord 브리지 등) — 세션을 직접 지정한 외부 봇.
            # 총괄은 스레드 없이 세션에 직접 보낸다. 채널 ID는 있으면 기록, 없어도 된다.
            if not folder.is_dir():
                die(f"폴더가 없습니다: {folder} (--session은 이미 돌고 있는 봇의 폴더에만)")
            ids = channel_id_of(folder)
            cid = a.channel_id or (ids[0] if len(ids) == 1 else "")
            e.update(tool=tool_of_engine(a.engine), mode="bot", session=a.session,
                     folder=str(folder), bot="", channel_id=cid)
        else:
            folder.mkdir(parents=True, exist_ok=True)
            e.update(tool=tool_of_engine(a.engine), mode="folder", folder=str(folder))
    r["employees"] = [x for x in r["employees"] if x["name"] != a.name] + [e]
    save_roster(root, r)
    print(f"직원 등록: {e['dept']} / {e['name']} [{e['tool']}/{e['mode']}]" + (f" 채널 {e['channel_id']}" if e["channel_id"] else ""))


def render(text: str, mapping: dict) -> str:
    for k, v in mapping.items():
        text = text.replace(k, v)
    return text


def directive_file(tool: str) -> tuple:
    if tool == "codex":
        return ("AGENTS.md", "")
    if tool == "gemini":
        return (".agents/rules/ai-company.md", AGY_HEADER)
    return ("CLAUDE.md", "")


def install_block(path: Path, body: str, header: str = ""):
    cur = path.read_text(encoding="utf-8") if path.exists() else header
    body = body.rstrip()
    if MARK_START in cur and MARK_END in cur:
        if cur.index(MARK_END) < cur.index(MARK_START):
            die(f"지침 블록 마커 순서가 잘못됐습니다: {path}")
        pre, rest = cur.split(MARK_START, 1)
        old, post = rest.split(MARK_END, 1)
        if old.strip("\n") == body:
            return None
        path.write_text(f"{pre}{MARK_START}\n{body}\n{MARK_END}{post}", encoding="utf-8")
        return f"지침 블록 갱신: {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cur + f"\n{MARK_START}\n{body}\n{MARK_END}\n", encoding="utf-8")
    return f"지침 블록 설치: {path}"


def remove_block(path: Path, header: str = ""):
    if not path.exists():
        return None
    cur = path.read_text(encoding="utf-8")
    if MARK_START not in cur or MARK_END not in cur:
        return None
    if cur.index(MARK_END) < cur.index(MARK_START):
        die(f"지침 블록 마커 순서가 잘못됐습니다: {path}")
    pre, rest = cur.split(MARK_START, 1)
    _, post = rest.split(MARK_END, 1)
    out = pre.rstrip("\n") + ("\n" if pre.strip() else "") + post.lstrip("\n")
    if not out.strip() or out.strip() == header.strip():
        path.unlink()
        return f"지침 블록 제거 후 빈 파일 삭제: {path}"
    path.write_text(out, encoding="utf-8")
    return f"지침 블록 제거: {path}"


def cmd_install(a) -> None:
    root = Path(a.root).expanduser().resolve()
    r = load_roster(root)
    done = []
    for d in COMPANY_DIRS + ["_templates"]:
        (root / d).mkdir(parents=True, exist_ok=True)
    for t in TEMPLATES:
        dst = root / "_templates" / t
        content = (ASSETS / t).read_text(encoding="utf-8")
        if t == "task.md":
            # task.md는 엔진 소유 템플릿 — 매 install마다 최신으로 갱신한다(기존 tasks/*/task.md는 건드리지 않음).
            if not dst.exists() or dst.read_text(encoding="utf-8") != content:
                dst.write_text(content, encoding="utf-8")
                done.append(f"템플릿 갱신: {dst}")
        elif not dst.exists():
            dst.write_text(content, encoding="utf-8")
            done.append(f"템플릿: {dst}")
    sess = root / "SESSION.md"
    if not sess.exists():
        sess.write_text((ASSETS / "SESSION.template.md").read_text(encoding="utf-8"), encoding="utf-8")
        done.append(f"SESSION.md 생성(템플릿): {sess}")
    inbox = str(root / "runtime" / "inbox")
    body = render((ASSETS / "company-block.md").read_text(encoding="utf-8"),
                  {"{ROOT}": str(root), "{INBOX}": inbox, "{NAME}": r["name"]})
    msg = install_block(root / "CLAUDE.md", body)
    manager_changed = bool(msg)
    if msg:
        done.append(msg)
    groups = {}
    order = []
    for e in r["employees"]:
        if e["mode"] == "on-demand" or not e["folder"]:
            continue
        folder = Path(e["folder"]).expanduser().resolve()
        if folder == root:
            done.append(f"WARN 회사 루트는 직원으로 등록할 수 없습니다(총괄 폴더) — 건너뜀: {e['name']}")
            continue
        if not folder.is_dir():
            done.append(f"WARN 폴더 없음 — 건너뜀: {folder} ({e['name']})")
            continue
        key = (folder, e["tool"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(e)
    for key in order:
        folder, tool = key
        emps = groups[key]
        fname, header = directive_file(tool)
        roles = "\n".join(f"- {e['dept']} · {e['name']}" for e in emps)
        eb = render((ASSETS / "employee-block.md").read_text(encoding="utf-8"),
                    {"{ROLES}": roles, "{ROOT}": str(root)})
        msg = install_block(folder / fname, eb, header)
        if msg:
            done.append(msg)
    # 총괄 블록이 새로 깔리거나 바뀌었고 회사 루트가 이미 폴더 봇이면 재시작 — 블록이 이미 최신이면
    # 봇을 괜히 끊지 않는다(멱등). 직원 블록만 바뀐 경우 총괄은 명부를 매 턴 읽으므로 재시작 불필요.
    if manager_changed:
        if getattr(a, "no_restart", False):
            if manager_bot_of(root)[0]:
                done.append("총괄 봇 재시작 생략(--no-restart) — 봇이 총괄 블록을 읽으려면 bot-restart <세션> 필요")
        else:
            done.extend(restart_manager_bot(root))
    print("\n".join(done) if done else "변경 없음(이미 설치됨)")


def cmd_remove(a) -> None:
    root = Path(a.root).expanduser().resolve()
    r = load_roster(root)
    done = []
    msg = remove_block(root / "CLAUDE.md")
    if msg:
        done.append(msg)
    for e in r["employees"]:
        if not e["folder"]:
            continue
        fname, header = directive_file(e["tool"])
        msg = remove_block(Path(e["folder"]).expanduser() / fname, header)
        if msg:
            done.append(msg)
    done.append("보존: 직원명부.json · SESSION.md · 업무요청/ · 결과물/ · tasks/ · runtime/ (삭제는 사용자 몫)")
    print("\n".join(done))


def which(name: str):
    return shutil.which(name)


MIN_AGENTLAYER = (1, 6, 0)
MIN_AGENTLAYER_STR = "1.6.0"


def parse_version(text: str):
    """첫 줄만 본다 — `agentlayer version`의 둘째 줄(`go1.25.7 darwin/amd64`)의 Go 툴체인 버전을
    agentlayer 버전으로 잘못 집지 않기 위함."""
    first_line = text.splitlines()[0] if text.strip() else ""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", first_line)
    return tuple(int(x) for x in m.groups()) if m else None


def version_ok(text: str) -> bool:
    ver = parse_version(text)
    return ver is not None and ver >= MIN_AGENTLAYER


def check_agentlayer() -> tuple:
    """(status, msg)를 돌려준다. status는 'ok' | 'warn' | 'fail'."""
    exe = which("agentlayer")
    if not exe:
        return ("fail", "agentlayer 없음 — brew install netwaif/tap/agentlayer && agentlayer init")
    try:
        out = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired) as ex:
        return ("fail", f"agentlayer version 실행 실패: {ex}")
    first_line = out.splitlines()[0].strip() if out.strip() else ""
    ver = parse_version(first_line)
    if ver is None:
        # 개발 빌드(`agentlayer dev (commit ...+dirty, ...)`)는 semver가 없다 — 메인테이너 머신을 막지 않는다.
        return ("warn", f"agentlayer 개발 빌드(버전 확인 불가): {first_line}")
    if not version_ok(first_line):
        return ("fail", f"agentlayer v{'.'.join(map(str, ver))} — {MIN_AGENTLAYER_STR} 이상 필요(brew upgrade netwaif/tap/agentlayer && agentlayer init)")
    return ("ok", f"agentlayer v{'.'.join(map(str, ver))}")


def task_rows() -> list:
    exe = which("agentlayer")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "task", "list", "--json"], capture_output=True, text=True, timeout=10).stdout
        rows = json.loads(out or "[]")
        return rows if isinstance(rows, list) else []
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []


def _strip_yaml_comment(line: str) -> str:
    """yaml 줄 주석 제거: 줄 선두(공백 제외) `#`는 줄 전체를 지우고, 그 외 ` #`(공백+해시) 이후는 잘라낸다."""
    if line.lstrip().startswith("#"):
        return ""
    idx = line.find(" #")
    if idx != -1:
        line = line[:idx]
    return line.rstrip()


def _decomment(text: str) -> str:
    return "\n".join(_strip_yaml_comment(ln) for ln in text.splitlines())


def parse_parents(text: str) -> list:
    """```yaml``` 블록의 parents: 를 읽는다. `parents: [A, B]` 한 줄 형태와
    `parents:\\n- A\\n- B` 여러 줄 리스트 형태를 모두 받는다(외부 yaml 의존 없음).
    줄 끝 ` # 주석`과 줄 전체 `# ...` 주석은 매칭 전에 제거하고, ID를 감싼 따옴표는 벗겨낸다."""
    text = _decomment(text)
    m = re.search(r"^parents:\s*\[(.*?)\]\s*$", text, re.M)
    if m:
        inner = m.group(1).strip()
        return [p.strip().strip("'\"") for p in inner.split(",") if p.strip()] if inner else []
    m = re.search(r"^parents:\s*$\n((?:^[ \t]*-[ \t]*\S.*$\n?)*)", text, re.M)
    if m:
        out = []
        for ln in m.group(1).splitlines():
            s = ln.strip()
            if s.startswith("-"):
                out.append(s[1:].strip().strip("'\""))
        return out
    return []


def broken_parents(root: Path) -> list:
    tasks_dir = root / "tasks"
    if not tasks_dir.is_dir():
        return []
    known = {p.name for p in tasks_dir.iterdir() if p.is_dir()}
    out = []
    for d in sorted(tasks_dir.glob("*/task.md")):
        tid = d.parent.name
        for parent in parse_parents(d.read_text(encoding="utf-8")):
            if parent not in known:
                out.append(f"tasks/{tid}: parents에 없는 업무 {parent}")
    return out


def active_tasks(root: Path) -> int:
    n = 0
    for d in (root / "tasks").glob("*/task.md"):
        m = re.search(r"^status:\s*(\S+)", d.read_text(encoding="utf-8"), re.M)
        if m and (m.group(1) in ("in_progress", "reviewing") or m.group(1).startswith("waiting_")):
            n += 1
    return n


def cmd_doctor(a) -> None:
    root = Path(a.root).expanduser().resolve()
    lines = []
    fail = False

    def ok(m): lines.append("OK   " + m)
    def warn(m): lines.append("WARN " + m)
    def bad(m):
        nonlocal fail
        fail = True
        lines.append("FAIL " + m)

    status, msg = check_agentlayer()
    {"ok": ok, "warn": warn, "fail": bad}[status](msg)
    for tool in ("bot-thread", "bot-up", "tmux"):
        (ok if which(tool) else bad)(f"{tool}: {which(tool) or '없음 — folder-bot 플러그인/tmux 설치'}")
    (ok if bots_json_path().exists() else warn)(f"folder-bot bots.json: {bots_json_path()}")

    if not roster_path(root).exists():
        warn(f"직원명부 없음 — companyctl init --root {root} 먼저")
        print("\n".join(lines))
        sys.exit(1 if fail else 0)

    r = load_roster(root)
    if r.get("version") != 1 or not isinstance(r.get("employees"), list):
        bad("직원명부 스키마: version/employees 이상")
    else:
        ok(f"직원명부: 부서 {len(r['departments'])}개, 직원 {len(r['employees'])}명")
    (ok if (root / "CLAUDE.md").exists() and MARK_START in (root / "CLAUDE.md").read_text(encoding="utf-8") else bad)(
        f"회사 CLAUDE.md 총괄 블록: {root / 'CLAUDE.md'}")
    for sub in ("pending", "received", "quarantine"):
        p = root / "runtime" / "inbox" / sub
        (ok if p.is_dir() else bad)(f"수신함 {sub}/: {p}")
    bots = read_bots()
    mgr = next((n for n, b in bots.items()
                if b.get("folder") and Path(b["folder"]).expanduser().resolve() == root), None)
    if mgr:
        ok(f"총괄 봇: {mgr} (세션 {bots[mgr].get('session', '')})")
    else:
        warn("총괄 봇 미등록 — 회사 루트에서 folder-bot configure-bot 실행")
    for d in r["departments"]:
        emps = [e for e in r["employees"] if e["dept"] == d]
        if not emps:
            warn(f"{d}: 직원 없음(호출형으로 운영)")
        for e in emps:
            if e["mode"] == "on-demand":
                ok(f"{d}/{e['name']}: 호출형")
                continue
            if e["mode"] == "folder":
                warn(f"{d}/{e['name']}: 폴더만 있음({e['folder']}) — configure-bot으로 봇 연결 뒤 `employee add --bot`로 갱신")
                continue
            folder = Path(e["folder"]).expanduser()
            fname, _ = directive_file(e["tool"])
            block_ok = (folder / fname).exists() and MARK_START in (folder / fname).read_text(encoding="utf-8")
            external = e["bot"] == ""  # --session으로 등록한 외부 봇: bots.json·채널 ID를 요구하지 않는다
            reg = external or e["bot"] in bots
            healthy = folder.is_dir() and block_ok and reg and (external or e["channel_id"])
            (ok if healthy else bad)(
                f"{d}/{e['name']} [{e['tool']}] 폴더={'있음' if folder.is_dir() else '없음'} 지침블록={'있음' if block_ok else '없음'} "
                f"bots.json={'외부(--session)' if external else ('등록' if reg else '미등록')} 채널={e['channel_id'] or '없음'} 세션={e['session']}")
    for row in task_rows():
        if row.get("state") in ("stale", "gone"):
            warn(f"업무 {row.get('task_id')} 세션 {row.get('session')}: {row.get('state')} — 재배정 또는 `agentlayer task done`")
    for m in broken_parents(root):
        warn(m)
    ok(f"활성 업무(tasks/): {active_tasks(root)}건")
    print("\n".join(lines))
    sys.exit(1 if fail else 0)


def main() -> None:
    p = argparse.ArgumentParser(prog="companyctl", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    ip = sub.add_parser("init", help="회사 루트·직원명부 생성")
    ip.add_argument("--root", default=".")
    ip.add_argument("--name")
    ip.add_argument("--depts", help="쉼표 구분 부서 목록(기본 9부서)")
    ip.set_defaults(fn=cmd_init)

    dp = sub.add_parser("dept", help="부서 추가/제거")
    dp.add_argument("action", choices=["add", "remove"])
    dp.add_argument("--root", default=".")
    dp.add_argument("--name", required=True)
    dp.set_defaults(fn=cmd_dept)

    lp = sub.add_parser("list", help="직원명부 출력")
    lp.add_argument("--root", default=".")
    lp.add_argument("--json", action="store_true")
    lp.set_defaults(fn=cmd_list)

    ep = sub.add_parser("employee", help="직원 등록/제거")
    ep.add_argument("action", choices=["add", "remove"])
    ep.add_argument("--root", default=".")
    ep.add_argument("--name", required=True)
    ep.add_argument("--dept")
    ep.add_argument("--bot", help="folder-bot bots.json의 봇 이름(기존 봇 등록)")
    ep.add_argument("--folder", help="새 부서 폴더(봇은 나중에 configure-bot으로)")
    ep.add_argument("--engine", choices=["claude", "codex", "agy", "gemini"], default=None, help="기본 claude(--env-file이면 그 ENGINE, 없으면 codex)")
    ep.add_argument("--on-demand", action="store_true", help="호출형(폴더·봇 없음)")
    ep.add_argument("--session", help="--folder와 함께: folder-bot 밖에서 도는 봇(LaunchAgent·브리지)의 tmux 세션 — 외부 봇 등록")
    ep.add_argument("--env-file", help="codex-discord 브리지 .env(.gemini) 경로 — TUI_PANE→세션, TUI_CHANNEL_ID→채널, CODEX_WORKDIR→폴더, ENGINE→엔진을 읽어 외부 봇으로 등록(라이브 TUI 모드 필수)")
    ep.add_argument("--channel-id")
    ep.add_argument("--replace", action="store_true")
    ep.set_defaults(fn=cmd_employee)

    inp = sub.add_parser("install", help="폴더·템플릿·지침 블록 설치(회사 루트가 폴더 봇이면 총괄 봇 재시작까지)")
    inp.add_argument("--root", default=".")
    inp.add_argument("--no-restart", action="store_true", help="총괄 블록이 바뀌어도 bot-restart를 부르지 않음")
    inp.set_defaults(fn=cmd_install)

    rp = sub.add_parser("remove", help="지침 블록 제거(기록 보존)")
    rp.add_argument("--root", default=".")
    rp.set_defaults(fn=cmd_remove)

    dop = sub.add_parser("doctor", help="읽기 전용 점검")
    dop.add_argument("--root", default=".")
    dop.set_defaults(fn=cmd_doctor)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
