#!/usr/bin/env python3
"""companyctl — AI 회사 생성기의 결정적 엔진.
정본은 <root>/직원명부.json 하나. 지침 파일은 마커 블록만 추가·제거하고 SESSION.md는 없을 때만 만든다.
비밀값은 읽지도 쓰지도 않는다. 표준 라이브러리만 쓴다.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROSTER = "직원명부.json"
DEFAULT_DEPTS = ["경영기획실", "콘텐츠전략팀", "기술개발팀", "크리에이티브팀", "기술검증팀",
                 "교육자료팀", "채널그로스팀", "커뮤니티·멤버십팀", "비즈니스운영팀"]
COMPANY_DIRS = ["업무요청", "참고자료", "결과물", "docs", "tasks",
                "runtime/inbox/pending", "runtime/inbox/received", "runtime/inbox/quarantine"]


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def roster_path(root: Path) -> Path:
    return root / ROSTER


def load_roster(root: Path) -> dict:
    p = roster_path(root)
    if not p.exists():
        die(f"직원명부가 없습니다: {p} — 먼저 `companyctl init --root {root}`")
    return json.loads(p.read_text(encoding="utf-8"))


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
        r = json.loads(p.read_text(encoding="utf-8"))
        changed = False
        if a.name and r.get("name") != a.name:
            r["name"] = a.name
            changed = True
        if changed:
            save_roster(root, r)
        print(f"직원명부 유지: {p} (직원 {len(r['employees'])}명, 부서 {len(r['departments'])}개)")
        return
    depts = [d.strip() for d in a.depts.split(",")] if a.depts else list(DEFAULT_DEPTS)
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

    for name, help_ in [("employee", "직원 등록/제거"), ("install", "폴더·템플릿·지침 블록 설치"),
                        ("remove", "지침 블록 제거(기록 보존)"), ("doctor", "읽기 전용 점검")]:
        sub.add_parser(name, help=help_).set_defaults(fn=lambda a: die("아직 구현되지 않은 명령", 2))

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
