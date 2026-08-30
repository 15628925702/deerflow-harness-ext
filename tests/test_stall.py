"""D2 no-progress / stall detection tests. Host-agnostic."""
from deerflow_harness_ext.core.engine import HarnessEngine
from deerflow_harness_ext.core.progress import NoProgressTracker
from deerflow_harness_ext.core.state import HarnessState
from deerflow_harness_ext.policies.stall import StallPolicy


def test_no_progress_tracker_counts_repeats():
    t = NoProgressTracker(stall_threshold=3)
    assert t.record("same") == 0
    assert t.record("same") == 1
    assert t.record("same") == 2
    assert t.stalled is False
    assert t.record("same") == 3
    assert t.stalled is True


def test_no_progress_resets_on_change():
    t = NoProgressTracker(stall_threshold=3)
    t.record("a")
    t.record("a")
    assert t.record("b") == 0
    assert t.streak == 0


def test_no_progress_none_output_resets():
    t = NoProgressTracker(stall_threshold=2)
    t.record("x")
    t.record("x")
    assert t.record(None) == 0


def test_no_progress_handles_dict_output():
    t = NoProgressTracker(stall_threshold=2)
    t.record({"a": 1})
    t.record({"a": 1})
    assert t.record({"a": 1}) == 2          # dict normalised -> repeat detected


def test_stall_policy_noop_below_threshold():
    st = HarnessState()
    eng = HarnessEngine(policies=[StallPolicy(threshold=4)])
    for _ in range(2):
        eng.after_model(st, {"tool_output": "same"})
    assert eng.summary()[-1]["action"] == "noop"


def test_stall_policy_emits_hint_when_stalled():
    st = HarnessState()
    eng = HarnessEngine(policies=[StallPolicy(threshold=2)])
    for _ in range(3):
        eng.after_model(st, {"tool_output": "same"})
    assert eng.summary()[-1]["action"] == "hint"


def test_stall_policy_state_persists_across_turns():
    st = HarnessState()
    eng = HarnessEngine(policies=[StallPolicy(threshold=2)])
    for _ in range(2):
        eng.after_model(st, {"tool_output": "same"})
    eng.after_model(st, {"tool_output": "same"})
    assert eng.summary()[-1]["action"] == "hint"
