from conftest import run


def test_help_runs(env):
    r = run(env, "--help")
    assert r.returncode == 0
    assert "init" in r.stdout and "doctor" in r.stdout
