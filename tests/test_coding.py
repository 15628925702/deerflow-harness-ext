"""D4 coding subagent tests. Host-agnostic (model/execute injected)."""
import json

from deerflow_harness_ext.coding.agent import CodingAgent
from deerflow_harness_ext.coding.config import CodingConfig
from deerflow_harness_ext.coding.prompt import build_system_prompt


def _fake_model(responses):
    state = {"i": 0}

    def model(transcript):
        r = responses[min(state["i"], len(responses) - 1)]
        state["i"] += 1
        return r

    return model


def test_system_prompt_lists_tools_and_rules():
    p = build_system_prompt(CodingConfig())
    assert "bash" in p and "read_file" in p
    assert "locate" in p
    assert "test" in p.lower()
    assert "changed_files" in p


def test_coding_agent_runs_tool_loop():
    executed = []

    def execute(tool, params):
        executed.append((tool, params))
        return {"status": "ok", "output": "OK"}

    responses = [
        json.dumps({"tool": "grep", "params": {"pattern": "TODO", "path": "."}}),
        json.dumps({"submit": {"changed_files": ["a.py"], "tests_run": ["t.py"],
                               "test_results": {"t.py": "pass"}, "diff_summary": "fixed",
                               "remaining_risks": [], "success": True}}),
    ]
    agent = CodingAgent(CodingConfig(max_turns=10), _fake_model(responses), execute)
    res = agent.run("fix bug", "/ws")
    assert res.success
    assert res.changed_files == ["a.py"]
    assert executed and executed[0][0] == "grep"


def test_coding_agent_disallows_unknown_tool():
    executed = []

    def execute(tool, params):
        executed.append(tool)
        return {"ok": True}

    responses = [
        json.dumps({"tool": "web_search", "params": {}}),
        json.dumps({"submit": {"success": True, "diff_summary": "x"}}),
    ]
    agent = CodingAgent(CodingConfig(tools=["bash"], max_turns=10),
                        _fake_model(responses), execute)
    res = agent.run("t", "/ws")
    assert executed == []            # web_search never dispatched


def test_coding_agent_returns_not_success_without_submit():
    agent = CodingAgent(
        CodingConfig(max_turns=3),
        _fake_model([json.dumps({"tool": "bash", "params": {"command": "x"}})]),
        lambda t, p: {"ok": True})
    res = agent.run("t", "/ws")
    assert res.success is False
    assert res.diff_summary == ""


def test_parse_action_extracts_from_prose():
    a = CodingAgent._parse_action('Let me check.\n{"tool": "grep", "params": {"p": "x"}}')
    assert a is not None and a["tool"] == "grep"


def test_parse_action_returns_none_for_garbage():
    assert CodingAgent._parse_action("nothing here") is None
