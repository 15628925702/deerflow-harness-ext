"""D0 tests: host-agnostic core runs policies and records decisions.

These do NOT require deerflow/langchain — only the stdlib and pytest.
"""
from deerflow_harness_ext.core.engine import HarnessEngine
from deerflow_harness_ext.core.state import HarnessState
from deerflow_harness_ext.policies.context import ContextPolicy
from deerflow_harness_ext.policies.failure import FailurePolicy


def test_engine_records_context_decision():
    st = HarnessState(context_fraction=0.9)
    eng = HarnessEngine(policies=[ContextPolicy(target_fraction=0.85)])
    eng.before_model(st)
    s = eng.summary()
    assert s[-1]["policy"] == "context"
    assert s[-1]["action"] == "compact"


def test_context_below_target_is_noop():
    st = HarnessState(context_fraction=0.5)
    eng = HarnessEngine(policies=[ContextPolicy(target_fraction=0.85)])
    eng.before_model(st)
    assert eng.summary()[-1]["action"] == "noop"


def test_failure_policy_emits_hint_after_repeats():
    st = HarnessState()
    eng = HarnessEngine(policies=[FailurePolicy(max_repeats=3)])
    for _ in range(3):
        eng.after_model(st, {"tool_name": "bash", "error": "command not found", "status": "error"})
    assert eng.summary()[-1]["action"] == "hint"
    assert st.recovery_hints


def test_failure_policy_noop_without_fingerprint():
    st = HarnessState()
    eng = HarnessEngine(policies=[FailurePolicy(max_repeats=3)])
    eng.after_model(st, {})
    assert eng.summary()[-1]["action"] == "noop"


def test_engine_show_is_displayable():
    st = HarnessState(context_fraction=0.95)
    eng = HarnessEngine(policies=[ContextPolicy()])
    eng.before_model(st)
    text = eng.show()
    assert "compact" in text
    assert isinstance(text, str)
