"""Adapter: normalize external host state into HarnessState (D7).

Hosts (DeerFlow ThreadState, Pi, ...) keep state in their own shapes. This
adapter is the single place that maps a plain serialisable mapping in/out of
HarnessState, so the host-agnostic core never depends on a host's schema.
A Pi adapter would implement the same two functions.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..core.state import HarnessState


def from_mapping(data: Optional[Dict[str, Any]]) -> HarnessState:
    """Build a HarnessState from a plain mapping (any host's state dict)."""
    s = HarnessState()
    if not data:
        return s
    s.failures = list(data.get("failures") or [])
    s.repeated_failures = dict(data.get("repeated_failures") or {})
    s.no_progress_turns = int(data.get("no_progress_turns") or 0)
    s.recovery_hints = list(data.get("recovery_hints") or [])
    s.context_fraction = float(data.get("context_fraction") or 0.0)
    s.extra = dict(data.get("extra") or {})
    return s


def to_mapping(state: HarnessState) -> Dict[str, Any]:
    """Serialize a HarnessState back to a plain mapping (host-neutral)."""
    return {
        "failures": list(state.failures),
        "repeated_failures": dict(state.repeated_failures),
        "no_progress_turns": state.no_progress_turns,
        "recovery_hints": list(state.recovery_hints),
        "context_fraction": state.context_fraction,
        "extra": dict(state.extra),
    }
