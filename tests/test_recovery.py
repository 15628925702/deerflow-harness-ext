"""D3 recovery policy tests. Host-agnostic."""
from deerflow_harness_ext.core.engine import HarnessEngine
from deerflow_harness_ext.core.state import HarnessState
from deerflow_harness_ext.policies.recovery import RecoveryPolicy


def _eng(max_injections=3):
    return HarnessEngine(policies=[RecoveryPolicy(max_injections=max_injections)])


def test_recovery_injects_and_removes_hint():
    st = HarnessState()
    st.recovery_hints.append("try X")
    d = _eng().before_model(st, {})[0]
    assert d.action == "inject_hint"
    assert st.recovery_hints == []          # transient: removed after inject


def test_recovery_noop_without_hints():
    st = HarnessState()
    assert _eng().before_model(st, {})[0].action == "noop"


def test_recovery_clears_on_new_evidence():
    st = HarnessState()
    st.recovery_hints.append("try X")
    _eng().after_model(st, {"status": "ok"})
    assert st.recovery_hints == []


def test_recovery_keeps_hint_without_evidence():
    st = HarnessState()
    st.recovery_hints.append("try X")
    _eng().after_model(st, {"status": "error"})
    assert st.recovery_hints == ["try X"]


def test_recovery_respects_max_injections():
    st = HarnessState()
    eng = _eng(max_injections=2)
    st.recovery_hints.append("h1")
    assert eng.before_model(st, {})[0].action == "inject_hint"
    st.recovery_hints.append("h2")
    assert eng.before_model(st, {})[0].action == "inject_hint"
    st.recovery_hints.append("h3")
    assert eng.before_model(st, {})[0].action == "noop"   # budget exhausted


def test_recovery_multiple_hints_injected_in_order():
    st = HarnessState()
    eng = _eng()
    st.recovery_hints.append("first")
    st.recovery_hints.append("second")
    assert eng.before_model(st, {})[0].data["hint"] == "first"
    assert eng.before_model(st, {})[0].data["hint"] == "second"
