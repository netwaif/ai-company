"""테스트 격리 — HOME을 임시 폴더로, PATH 앞에 가짜 agentlayer·bot-thread·bot-up·tmux.
실제 바이너리를 부르면 표식 파일이 남아 즉시 실패한다(folder-bot conftest 방식)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

COMPANYCTL = Path(__file__).parent.parent / "plugins/ai-company/skills/configure-company/generator/companyctl.py"

FAKES = {
    "agentlayer": '#!/bin/sh\ncase "$1" in\n  version) echo "agentlayer v1.6.0 (commit abc1234, 2026-09-14)";;\n  task) echo "[]";;\n  *) echo "fake agentlayer $*";;\nesac\n',
    "bot-thread": '#!/bin/sh\necho "fake bot-thread $*"\n',
    "bot-up": '#!/bin/sh\necho "fake bot-up $*"\n',
    "tmux": '#!/bin/sh\necho "fake tmux $*"\n',
}


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    shim = tmp_path / "shim"
    shim.mkdir()
    for name, body in FAKES.items():
        p = shim / name
        p.write_text(body)
        p.chmod(0o755)
    return {"HOME": str(home), "PATH": f"{shim}:{os.environ.get('PATH', '')}",
            "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}


def run(env, *args):
    return subprocess.run([sys.executable, str(COMPANYCTL), *args], capture_output=True, text=True, env=env)


def write_bots_json(env, bots: dict):
    cfg = Path(env["HOME"]) / ".config/folder-bot"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "bots.json").write_text(__import__("json").dumps(bots, ensure_ascii=False))


def write_access(folder: Path, channel_ids):
    st = folder / ".discord-state"
    st.mkdir(parents=True, exist_ok=True)
    groups = {cid: {"requireMention": False, "allowFrom": []} for cid in channel_ids}
    (st / "access.json").write_text(__import__("json").dumps({"dmPolicy": "allowlist", "allowFrom": [], "groups": groups, "pending": {}}))
