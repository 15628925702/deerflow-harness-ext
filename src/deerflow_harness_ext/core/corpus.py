"""Detector corpus for cross-host decision consistency (D7).

The host-agnostic core + policies are meant to be reused across hosts
(DeerFlow, Pi, ...). To prove the decisions are a pure function of the policy
chain and the context fed in — not of any host adapter — we run a fixed corpus
of tool-outcome cases and compare the decision sequences.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .state import HarnessState


@dataclass
class DetectorCase:
    """One standard input to a policy engine."""

    name: str
    ctx: Dict[str, Any]


DEFAULT_CORPUS: List[DetectorCase] = [
    DetectorCase("success",
                 {"tool_name": "bash", "status": "ok", "tool_output": "done"}),
    DetectorCase("repeated_error",
                 {"tool_name": "bash", "error": "command not found: x", "status": "error"}),
    DetectorCase("dangerous_cmd",
                 {"tool_name": "bash", "tool_args": {"command": "rm -rf /"}}),
    DetectorCase("protected_path",
                 {"tool_name": "read_file", "tool_args": {"path": "/etc/passwd"}}),
    DetectorCase("mutating_write",
                 {"tool_name": "write_file", "tool_args": {"path": "/tmp/a.py"}}),
    DetectorCase("stall_twice",
                 {"tool_output": "same"}),
    DetectorCase("stall_threshold",
                 {"tool_output": "same"}),
]


def run_corpus(engine, cases: List[DetectorCase] = None) -> List[Dict[str, Any]]:
    """Run each case through `engine` with a fresh state.

    A fresh HarnessState per case makes every decision a pure function of the
    policy chain + ctx, so two hosts that feed the same ctx get identical
    decision sequences regardless of how the host serialises state.
    """
    out: List[Dict[str, Any]] = []
    for case in (cases or DEFAULT_CORPUS):
        st = HarnessState()
        decisions = engine.after_model(st, dict(case.ctx))
        out.append({"case": case.name, "decisions": [d.as_dict() for d in decisions]})
    return out
