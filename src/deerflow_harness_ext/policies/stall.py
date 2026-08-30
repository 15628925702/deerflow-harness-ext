"""Stall policy: detects no-progress via repeated identical tool outputs (D2)."""
from __future__ import annotations

from typing import Any, Dict

from ..core.decisions import PolicyDecision
from ..core.engine import Policy
from ..core.progress import NoProgressTracker


class StallPolicy(Policy):
    """Emit a hint when the loop stops making progress (same output repeated).

    Keeps a NoProgressTracker in HarnessState.extra so the streak persists
    across model turns for a single episode.
    """

    name = "stall"

    def __init__(self, threshold: int = 5) -> None:
        self.threshold = max(1, int(threshold))

    def _tracker(self, state):
        tr = state.extra.get("_stall")
        if tr is None:
            tr = NoProgressTracker(stall_threshold=self.threshold)
            state.extra["_stall"] = tr
        return tr

    def after_model(self, state, ctx: Dict[str, Any]) -> PolicyDecision:
        ctx = ctx or {}
        tracker = self._tracker(state)
        streak = tracker.record(ctx.get("tool_output"))
        if tracker.stalled:
            return PolicyDecision(self.name, "hint",
                                  reason=f"no-progress: same output x{streak}",
                                  data={"streak": streak})
        return PolicyDecision(self.name, "noop")
