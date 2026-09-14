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


def test_employee_add_bot_missing_folder_field(env, tmp_path):
    root = _init(env, tmp_path)
    write_bots_json(env, {"nofolder": {"engine": "claude", "session": "s"}})
    r = run(env, "employee", "add", "--root", str(root), "--dept", "비즈니스운영팀", "--name", "x", "--bot", "nofolder")
    assert r.returncode != 0
    assert "folder" in r.stderr
    assert "Traceback" not in r.stderr


def test_corrupted_roster_json_dies_cleanly(env, tmp_path):
    root = _init(env, tmp_path)
    (root / "직원명부.json").write_text("{not json")
    r = run(env, "list", "--root", str(root))
    assert r.returncode != 0
    assert "손상" in r.stderr
    assert "Traceback" not in r.stderr


def test_corrupted_bots_json_dies_cleanly(env, tmp_path):
    root = _init(env, tmp_path)
    cfg = Path(env["HOME"]) / ".config/folder-bot"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "bots.json").write_text("{not json")
    r = run(env, "employee", "add", "--root", str(root), "--dept", "비즈니스운영팀", "--name", "x", "--bot", "collab")
    assert r.returncode != 0
    assert "손상" in r.stderr
    assert "Traceback" not in r.stderr


def test_init_depts_dedupe_and_strip_empty(env, tmp_path):
    root = tmp_path / "c"
    run(env, "init", "--root", str(root), "--depts", "a,,a, b ,")
    assert json.loads((root / "직원명부.json").read_text())["departments"] == ["a", "b"]
    r = run(env, "init", "--root", str(tmp_path / "c2"), "--depts", ",,")
    assert r.returncode != 0


def test_init_on_corrupted_roster_dies_cleanly(env, tmp_path):
    root = _init(env, tmp_path)
    (root / "직원명부.json").write_text("{not json")
    r = run(env, "init", "--root", str(root))
    assert r.returncode != 0
    assert "손상" in r.stderr
    assert "Traceback" not in r.stderr


MS, ME = "<!-- store:ai-company:start -->", "<!-- store:ai-company:end -->"


def test_install_creates_templates_blocks_and_session(env, tmp_path):
    root = _init(env, tmp_path)
    folder = tmp_path / "collab"
    folder.mkdir()
    (folder / "CLAUDE.md").write_text("# collab\n기존 규칙\n")
    write_bots_json(env, {"collab": {"engine": "claude", "folder": str(folder), "session": "collab-bot"}})
    write_access(folder, ["1"])
    run(env, "employee", "add", "--root", str(root), "--dept", "비즈니스운영팀", "--name", "사업운영", "--bot", "collab")
    r = run(env, "install", "--root", str(root))
    assert r.returncode == 0, r.stderr
    for f in ["_templates/task.md", "_templates/업무요청.md", "_templates/log.md", "SESSION.md", "CLAUDE.md"]:
        assert (root / f).exists(), f
    cm = (root / "CLAUDE.md").read_text()
    assert MS in cm and ME in cm and str(root) in cm and "runtime/inbox" in cm and "총괄 절차" in cm
    em = (folder / "CLAUDE.md").read_text()
    assert em.startswith("# collab\n기존 규칙\n") and MS in em and "비즈니스운영팀" in em and "사업운영" in em


def test_install_idempotent_and_never_touches_existing_session(env, tmp_path):
    root = _init(env, tmp_path)
    (root / "SESSION.md").write_text("내 기록\n")
    run(env, "install", "--root", str(root))
    first = (root / "CLAUDE.md").read_text()
    run(env, "install", "--root", str(root))
    assert (root / "CLAUDE.md").read_text() == first
    assert (root / "SESSION.md").read_text() == "내 기록\n"


def test_install_engine_specific_files(env, tmp_path):
    root = _init(env, tmp_path)
    cx, gy = tmp_path / "cx", tmp_path / "gy"
    cx.mkdir(); gy.mkdir()
    write_bots_json(env, {"cx": {"engine": "codex", "folder": str(cx), "session": "cx"},
                          "gy": {"engine": "agy", "folder": str(gy), "session": "gy"}})
    write_access(cx, ["1"]); write_access(gy, ["2"])
    run(env, "employee", "add", "--root", str(root), "--dept", "크리에이티브팀", "--name", "비주얼", "--bot", "cx")
    run(env, "employee", "add", "--root", str(root), "--dept", "커뮤니티·멤버십팀", "--name", "지원", "--bot", "gy")
    assert run(env, "install", "--root", str(root)).returncode == 0
    assert MS in (cx / "AGENTS.md").read_text()
    g = (gy / ".agents/rules/ai-company.md").read_text()
    assert g.startswith("---\ntrigger: always_on\n---\n") and MS in g


def test_remove_restores_originals(env, tmp_path):
    root = _init(env, tmp_path)
    folder = tmp_path / "collab"
    folder.mkdir()
    (folder / "CLAUDE.md").write_text("# collab\n기존 규칙\n")
    write_bots_json(env, {"collab": {"engine": "claude", "folder": str(folder), "session": "collab-bot"}})
    write_access(folder, ["1"])
    run(env, "employee", "add", "--root", str(root), "--dept", "비즈니스운영팀", "--name", "사업운영", "--bot", "collab")
    run(env, "install", "--root", str(root))
    r = run(env, "remove", "--root", str(root))
    assert r.returncode == 0, r.stderr
    assert (folder / "CLAUDE.md").read_text() == "# collab\n기존 규칙\n"
    assert not (root / "CLAUDE.md").exists()          # 블록만 있던 파일은 삭제
    assert (root / "직원명부.json").exists() and (root / "SESSION.md").exists()   # 기록 보존
