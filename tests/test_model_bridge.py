"""D6 ModelBridge tests. Host-agnostic."""
from deerflow_harness_ext.coding.model_bridge import ModelBridge


def test_query_prepends_system():
    calls = []

    def q(messages):
        calls.append(messages)
        return "hi"

    b = ModelBridge(q)
    r = b.query("SYS", [{"role": "user", "content": "u"}])
    assert r == "hi"
    assert calls[0][0] == {"role": "system", "content": "SYS"}
    assert b.call_count == 1


def test_query_records_trajectory():
    def q(messages):
        return "reply"
    b = ModelBridge(q)
    b.query("S", [])
    assert len(b.trajectory) == 1
    assert b.trajectory[0]["reply"] == "reply"


def test_query_preserves_transcript():
    def q(messages):
        return "r"
    b = ModelBridge(q)
    b.query("S", [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}])
    assert len(b.trajectory[0]["transcript"]) == 2
