"""DryRunLedger tests. Host-agnostic."""
from deerflow_harness_ext.core.decisions import PolicyDecision
from deerflow_harness_ext.telemetry import DryRunLedger


def test_ledger_add_and_dump():
    l = DryRunLedger()
    l.add(PolicyDecision("context", "compact", reason="x"))
    l.extend([PolicyDecision("failure", "noop")])
    out = l.dump()
    assert len(out) == 2
    assert out[0]["policy"] == "context"
    assert out[0]["action"] == "compact"
    assert out[0]["reason"] == "x"
    assert out[1]["policy"] == "failure"


def test_ledger_add_plain_dict():
    l = DryRunLedger()
    l.add({"a": 1})
    assert l.dump() == [{"a": 1}]


def test_ledger_is_append_only_snapshot():
    l = DryRunLedger()
    l.add(PolicyDecision("context", "noop"))
    snap = l.dump()
    snap.append({"fake": True})          # mutating the returned list must not affect the ledger
    assert len(l.dump()) == 1
