"""D2 failure fingerprinting + failure policy tests. Host-agnostic."""
from deerflow_harness_ext.core.engine import HarnessEngine
from deerflow_harness_ext.core.failure import fingerprint_tool_outcome
from deerflow_harness_ext.core.state import HarnessState
from deerflow_harness_ext.policies.failure import FailurePolicy


def test_fingerprint_stable_for_same_error():
    a = fingerprint_tool_outcome("bash", error="command not found: foo")
    b = fingerprint_tool_outcome("bash", error="command not found: foo")
    assert a == b


def test_fingerprint_differs_for_different_errors():
    a = fingerprint_tool_outcome("bash", error="not found")
    b = fingerprint_tool_outcome("bash", error="permission denied")
    assert a != b


def test_fingerprint_ignores_noise():
    a = fingerprint_tool_outcome("bash", error="Err [2026-08-29 10:00:00] pid 1234 failed, 0xdeadbeef, in 12ms")
    b = fingerprint_tool_outcome("bash", error="Err [2026-08-28 09:00:00] pid 9999 failed, 0xcafebabe, in 3s")
    assert a == b


def test_fingerprint_output_dict_is_key_order_stable():
    a = fingerprint_tool_outcome("run", output={"status": "boom", "msg": "kaboom"})
    b = fingerprint_tool_outcome("run", output={"msg": "kaboom", "status": "boom"})
    assert a == b


def test_failure_policy_hint_after_repeats():
    st = HarnessState()
    eng = HarnessEngine(policies=[FailurePolicy(max_repeats=2)])
    for _ in range(2):
        eng.after_model(st, {"tool_name": "bash", "error": "no", "status": "error"})
    assert eng.summary()[-1]["action"] == "hint"
    assert st.recovery_hints


def test_failure_policy_ignores_success():
    st = HarnessState()
    eng = HarnessEngine(policies=[FailurePolicy(max_repeats=1)])
    eng.after_model(st, {"tool_name": "bash", "status": "ok", "tool_output": "done"})
    assert eng.summary()[-1]["action"] == "noop"
    assert st.failures == []


def test_failure_policy_counts_distinct_failures_separately():
    st = HarnessState()
    eng = HarnessEngine(policies=[FailurePolicy(max_repeats=3)])
    # two different errors, two calls each -> no single fingerprint hits 3
    for _ in range(2):
        eng.after_model(st, {"tool_name": "bash", "error": "errA", "status": "error"})
    for _ in range(2):
        eng.after_model(st, {"tool_name": "bash", "error": "errB", "status": "error"})
    assert eng.summary()[-1]["action"] == "noop"
    assert len(st.repeated_failures) == 2
