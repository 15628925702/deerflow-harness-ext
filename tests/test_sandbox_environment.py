"""D6 SandboxEnvironment bridge tests. Host-agnostic (fake sandbox)."""
import pytest

from deerflow_harness_ext.coding.sandbox_environment import SandboxEnvironment


class FakeSandbox:
    def __init__(self):
        self.commands = []

    def execute_command(self, command, env=None, timeout=None):
        self.commands.append(command)
        return "OK"


def test_execute_wraps_with_cd():
    sb = FakeSandbox()
    env = SandboxEnvironment(sb, "/ws")
    r = env.execute({"command": "ls"}, cwd="sub")
    assert sb.commands[0].startswith("cd")      # wrapped with cd
    assert "ls" in sb.commands[0]               # command survives
    assert "sub" in sb.commands[0]              # cwd present (relative, cross-platform)
    assert r["returncode"] == 0


def test_execute_rejects_escaping_cwd():
    sb = FakeSandbox()
    env = SandboxEnvironment(sb, "/ws")
    with pytest.raises(ValueError):
        env.execute({"command": "ls"}, cwd="../../etc")


def test_execute_records_action():
    sb = FakeSandbox()
    env = SandboxEnvironment(sb, "/ws")
    env.execute({"command": "x"})
    assert len(env.records) == 1
    assert env.records[0].command == "x"
    assert env.records[0].output_digest
    assert env.records[0].started_at_diff


def test_execute_error_returns_code_1():
    class Bad:
        def execute_command(self, command, env=None, timeout=None):
            raise RuntimeError("boom")
    env = SandboxEnvironment(Bad(), "/ws")
    r = env.execute({"command": "x"})
    assert r["returncode"] == 1
    assert "boom" in r["output"]
