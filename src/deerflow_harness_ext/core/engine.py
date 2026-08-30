"""HarnessEngine: runs a chain of policies and records every decision.

This is the dry-run ledger — every policy decision is appended so it can be
displayed / audited / A/B compared. The engine is host-agnostic: policies only
see HarnessState and a plain context dict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .decisions import PolicyDecision
from .state import HarnessState


class Policy:
    """Base policy. Subclass and override before_model / after_model."""

    name = "base"

    def before_model(self, state: HarnessState, ctx: Dict[str, Any]) -> PolicyDecision:
        return PolicyDecision(self.name, "noop")

    def after_model(self, state: HarnessState, ctx: Dict[str, Any]) -> PolicyDecision:
        return PolicyDecision(self.name, "noop")


@dataclass
class HarnessEngine:
    """Runs policies around model turns; all decisions go to the ledger."""

    policies: List[Policy] = field(default_factory=list)
    ledger: List[PolicyDecision] = field(default_factory=list)

    def before_model(self, state: HarnessState, ctx: Optional[Dict[str, Any]] = None) -> List[PolicyDecision]:
        decisions = [p.before_model(state, ctx or {}) for p in self.policies]
        return self._record(decisions)

    def after_model(self, state: HarnessState, ctx: Optional[Dict[str, Any]] = None) -> List[PolicyDecision]:
        decisions = [p.after_model(state, ctx or {}) for p in self.policies]
        return self._record(decisions)

    def _record(self, decisions: Sequence[PolicyDecision]) -> List[PolicyDecision]:
        self.ledger.extend(decisions)
        return list(decisions)

    def summary(self) -> List[Dict[str, Any]]:
        """Ledger of all decisions, ready to display / audit / A/B."""
        return [d.as_dict() for d in self.ledger]

    def show(self, tail: int = 10) -> str:
        """Human-readable display of the last `tail` decisions (D0 exit criterion)."""
        rows = self.ledger[-tail:]
        if not rows:
            return "(no decisions recorded)"
        lines = [f"[{i}] {d.policy:<10} {d.action:<18} {d.reason}" for i, d in enumerate(rows)]
        return "\n".join(lines)
