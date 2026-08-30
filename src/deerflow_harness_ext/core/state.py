"""Harness control state (short-lived, host-agnostic).

Distinct from long-term MemoryStorage: this holds transient failure counts,
no-progress tracking, recovery hints, and the policy decision ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HarnessState:
    """Transient policy state around the agent's model loop."""

    failures: List[str] = field(default_factory=list)            # failure fingerprints
    repeated_failures: Dict[str, int] = field(default_factory=dict)
    no_progress_turns: int = 0
    recovery_hints: List[str] = field(default_factory=list)
    context_fraction: float = 0.0                                # 0..1
    decisions: List[Any] = field(default_factory=list)           # latest decision objects
    extra: Dict[str, Any] = field(default_factory=dict)

    def reset_transient(self) -> None:
        """Called before a new model turn; keeps long-running counters."""
        self.decisions = []
