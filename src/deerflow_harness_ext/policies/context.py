"""Context policy: suggests compaction when context is near the target.

Coexists with DeerFlow's own SummarizationMiddleware; this only signals *when*
to compact and what must be preserved — it does not build a second summary.
"""
from __future__ import annotations

from typing import Any, Dict

from ..core.decisions import PolicyDecision
from ..core.engine import Policy
from ..core.state import HarnessState


class ContextPolicy(Policy):
    name = "context"

    # Fields the summarizer must not drop when compacting.
    PRESERVE_FIELDS = ["recovery_hints", "repeated_failures", "failures"]

    def __init__(self, target_fraction: float = 0.85) -> None:
        # clamp to [0, 1] so invalid config cannot make the policy always-fire
        self.target_fraction = min(1.0, max(0.0, float(target_fraction)))

    def before_model(self, state: HarnessState, ctx: Dict[str, Any]) -> PolicyDecision:
        if state.context_fraction >= self.target_fraction:
            return PolicyDecision(
                self.name, "compact",
                reason=f"context at {state.context_fraction:.0%} >= {self.target_fraction:.0%}",
                data={"preserve": list(self.PRESERVE_FIELDS)},
            )
        return PolicyDecision(self.name, "noop")
