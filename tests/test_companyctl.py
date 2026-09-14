import json
from pathlib import Path
from conftest import run, write_bots_json, write_access


def test_help_runs(env):
    r = run(env, "--help")
    assert r.returncode == 0
    assert "init" in r.stdout and "doctor" in r.stdout


def test_init_creates_roster_and_dirs(env, tmp_path):
    root = tmp_path / "company"
    r = run(env, "init", "--root", str(root), "--name", "AI 치트키")
    assert r.returncode == 0, r.stderr
    roster = json.loads((root / "직원명부.json").read_text())
    assert roster["version"] == 1 and roster["name"] == "AI 치트키"
    assert roster["departments"][0] == "경영기획실" and len(roster["departments"]) == 9
    assert roster["employees"] == []
    for d in ["업무요청", "참고자료", "결과물", "docs", "tasks", "runtime/inbox/pending", "runtime/inbox/received", "runtime/inbox/quarantine"]:
        assert (root / d).is_dir(), d


def test_init_is_idempotent_and_keeps_employees(env, tmp_path):
    root = tmp_path / "c"
    run(env, "init", "--root", str(root), "--name", "회사")
    p = root / "직원명부.json"
    r = json.loads(p.read_text())
    r["employees"].append({"dept": "경영기획실", "name": "총괄", "tool": "claude", "mode": "bot", "session": "s", "folder": str(root), "bot": "company", "channel_id": "1"})
    p.write_text(json.dumps(r, ensure_ascii=False))
    assert run(env, "init", "--root", str(root)).returncode == 0
    assert len(json.loads(p.read_text())["employees"]) == 1
    assert json.loads(p.read_text())["name"] == "회사"


def test_init_custom_depts(env, tmp_path):
    root = tmp_path / "c"
    run(env, "init", "--root", str(root), "--depts", "경영기획실,학원운영팀")
    assert json.loads((root / "직원명부.json").read_text())["departments"] == ["경영기획실", "학원운영팀"]


def test_dept_add_remove_and_list(env, tmp_path):
    root = tmp_path / "c"
    run(env, "init", "--root", str(root))
    assert run(env, "dept", "add", "--root", str(root), "--name", "학원운영팀").returncode == 0
    assert run(env, "dept", "add", "--root", str(root), "--name", "학원운영팀").returncode == 0  # 멱등
    depts = json.loads((root / "직원명부.json").read_text())["departments"]
    assert depts.count("학원운영팀") == 1
    r = run(env, "list", "--root", str(root))
    assert "학원운영팀" in r.stdout and "경영기획실" in r.stdout
    assert run(env, "dept", "remove", "--root", str(root), "--name", "학원운영팀").returncode == 0
    assert "학원운영팀" not in json.loads((root / "직원명부.json").read_text())["departments"]
    r = run(env, "list", "--root", str(root), "--json")
    assert json.loads(r.stdout)["version"] == 1


def test_commands_require_init(env, tmp_path):
    r = run(env, "list", "--root", str(tmp_path / "nope"))
    assert r.returncode != 0 and "init" in r.stderr


def _init(env, tmp_path):
    root = tmp_path / "c"
    run(env, "init", "--root", str(root))
    return root


def test_employee_add_from_bot(env, tmp_path):
    root = _init(env, tmp_path)
    folder = tmp_path / "work" / "collab"
    folder.mkdir(parents=True)
    write_bots_json(env, {"collab": {"engine": "claude", "folder": str(folder), "session": "collab-bot"}})
    write_access(folder, ["1542142326384754748"])
    r = run(env, "employee", "add", "--root", str(root), "--dept", "비즈니스운영팀", "--name", "사업운영 매니저", "--bot", "collab")
    assert r.returncode == 0, r.stderr
    e = json.loads((root / "직원명부.json").read_text())["employees"][0]
    assert e == {"dept": "비즈니스운영팀", "name": "사업운영 매니저", "tool": "claude", "mode": "bot",
                 "session": "collab-bot", "folder": str(folder), "bot": "collab", "channel_id": "1542142326384754748"}


def test_employee_add_bot_engine_agy_maps_to_gemini_and_needs_channel_when_ambiguous(env, tmp_path):
    root = _init(env, tmp_path)
    folder = tmp_path / "g"
    folder.mkdir()
    write_bots_json(env, {"community": {"engine": "agy", "folder": str(folder), "session": "community-agy"}})
    write_access(folder, ["100", "200"])
    r = run(env, "employee", "add", "--root", str(root), "--dept", "커뮤니티·멤버십팀", "--name", "시청자 지원", "--bot", "community")
    assert r.returncode != 0 and "--channel-id" in r.stderr
    r = run(env, "employee", "add", "--root", str(root), "--dept", "커뮤니티·멤버십팀", "--name", "시청자 지원", "--bot", "community", "--channel-id", "200")
    assert r.returncode == 0, r.stderr
    e = json.loads((root / "직원명부.json").read_text())["employees"][0]
    assert e["tool"] == "gemini" and e["channel_id"] == "200"


def test_employee_add_unknown_bot_or_dept_fails(env, tmp_path):
    root = _init(env, tmp_path)
    write_bots_json(env, {})
    r = run(env, "employee", "add", "--root", str(root), "--dept", "비즈니스운영팀", "--name", "x", "--bot", "nope")
    assert r.returncode != 0 and "bots.json" in r.stderr
    r = run(env, "employee", "add", "--root", str(root), "--dept", "없는팀", "--name", "x", "--on-demand")
    assert r.returncode != 0 and "부서" in r.stderr


def test_employee_add_folder_and_on_demand(env, tmp_path):
    root = _init(env, tmp_path)
    newf = tmp_path / "new-dept"
    r = run(env, "employee", "add", "--root", str(root), "--dept", "기술개발팀", "--name", "AI 개발자", "--folder", str(newf), "--engine", "codex")
    assert r.returncode == 0, r.stderr
    assert newf.is_dir()
    r = run(env, "employee", "add", "--root", str(root), "--dept", "기술검증팀", "--name", "QA 담당", "--on-demand")
    assert r.returncode == 0, r.stderr
    emps = json.loads((root / "직원명부.json").read_text())["employees"]
    assert emps[0]["mode"] == "folder" and emps[0]["tool"] == "codex" and emps[0]["session"] == ""
    assert emps[1] == {"dept": "기술검증팀", "name": "QA 담당", "tool": "claude", "mode": "on-demand", "session": "", "folder": "", "bot": "", "channel_id": ""}


def test_employee_add_duplicate_needs_replace_and_remove(env, tmp_path):
    root = _init(env, tmp_path)
    run(env, "employee", "add", "--root", str(root), "--dept", "기술검증팀", "--name", "QA 담당", "--on-demand")
    r = run(env, "employee", "add", "--root", str(root), "--dept", "기술검증팀", "--name", "QA 담당", "--on-demand")
    assert r.returncode != 0 and "--replace" in r.stderr
    r = run(env, "employee", "add", "--root", str(root), "--dept", "채널그로스팀", "--name", "QA 담당", "--on-demand", "--replace")
    assert r.returncode == 0
    emps = json.loads((root / "직원명부.json").read_text())["employees"]
    assert len(emps) == 1 and emps[0]["dept"] == "채널그로스팀"
    assert run(env, "employee", "remove", "--root", str(root), "--name", "QA 담당").returncode == 0
    assert json.loads((root / "직원명부.json").read_text())["employees"] == []
    assert run(env, "employee", "remove", "--root", str(root), "--name", "QA 담당").returncode != 0
