"""D7 detector corpus + state adapter tests. Host-agnostic."""
from deerflow_harness_ext.core.corpus import DEFAULT_CORPUS, DetectorCase, run_corpus
from deerflow_harness_ext.core.engine import HarnessEngine
from deerflow_harness_ext.core.state import HarnessState
from deerflow_harness_ext.deerflow.state_adapter import from_mapping, to_mapping
from deerflow_harness_ext.policies.context import ContextPolicy
from deerflow_harness_ext.policies.failure import FailurePolicy
from deerflow_harness_ext.policies.permissions import PermissionPolicy
from deerflow_harness_ext.policies.stall import StallPolicy


def _full_engine():
    return HarnessEngine(policies=[
        FailurePolicy(max_repeats=2),
        StallPolicy(threshold=2),
        PermissionPolicy(mode="default"),
        ContextPolicy(target_fraction=0.9),
    ])


def test_corpus_repeatable():
    e = _full_engine()
    assert run_corpus(e) == run_corpus(e)


def test_corpus_cross_host_identical():
    # two "hosts" both run the same host-agnostic engine + corpus
    assert run_corpus(_full_engine()) == run_corpus(_full_engine())


def test_corpus_sensitive_to_policy():
    # removing the permission policy must change the corpus output
    base = run_corpus(_full_engine())
    lean = run_corpus(HarnessEngine(policies=[ContextPolicy(target_fraction=0.9)]))
    assert base != lean


def test_corpus_protected_path_is_denied():
    out = run_corpus(_full_engine())
    entry = next(x for x in out if x["case"] == "protected_path")
    decisions = entry["decisions"]
    assert any(d["action"] == "deny" for d in decisions)


def test_state_adapter_roundtrip():
    s = HarnessState()
    s.failures = ["a"]
    s.repeated_failures = {"fp": 2}
    s.context_fraction = 0.5
    s.recovery_hints = ["h"]
    m = to_mapping(s)
    s2 = from_mapping(m)
    assert s2.failures == ["a"]
    assert s2.repeated_failures == {"fp": 2}
    assert s2.context_fraction == 0.5
    assert s2.recovery_hints == ["h"]


def test_state_adapter_empty():
    assert from_mapping(None).failures == []
    assert from_mapping({}).context_fraction == 0.0
