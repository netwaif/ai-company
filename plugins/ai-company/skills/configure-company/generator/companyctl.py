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


def tool_of_engine(engine: str) -> str:
    return {"claude": "claude", "codex": "codex", "agy": "gemini", "gemini": "gemini"}.get(engine, engine)


def cmd_employee(a) -> None:
    root = Path(a.root).expanduser().resolve()
    r = load_roster(root)
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
        if not cid:
            die(f"채널 ID를 정할 수 없습니다(access.json groups: {ids}) — --channel-id <ID>로 지정")
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
    ep.add_argument("--engine", choices=["claude", "codex", "agy", "gemini"], default="claude")
    ep.add_argument("--on-demand", action="store_true", help="호출형(폴더·봇 없음)")
    ep.add_argument("--session", help="--folder와 함께: folder-bot 밖에서 도는 봇(LaunchAgent·브리지)의 tmux 세션 — 외부 봇 등록")
    ep.add_argument("--channel-id")
    ep.add_argument("--replace", action="store_true")
    ep.set_defaults(fn=cmd_employee)

    inp = sub.add_parser("install", help="폴더·템플릿·지침 블록 설치")
    inp.add_argument("--root", default=".")
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
