"""Recovery policy: surfaces transient recovery hints to the next model call (D3)."""
from __future__ import annotations

from typing import Any, Dict

from ..core.decisions import PolicyDecision
from ..core.engine import Policy


class RecoveryPolicy(Policy):
    """Injects transient recovery hints into the next model call.

    Hints come from other policies (FailurePolicy / StallPolicy append to
    state.recovery_hints). RecoveryPolicy decides how to surface them:
      - a hint is injected at most once, then removed (transient)
      - new evidence (a successful tool result) clears pending advice
      - at most max_injections total, to avoid nagging the model
    """

    name = "recovery"

    def __init__(self, max_injections: int = 3) -> None:
        self.max_injections = max(1, int(max_injections))

    def before_model(self, state, ctx: Dict[str, Any]) -> PolicyDecision:
        if not state.recovery_hints:
            return PolicyDecision(self.name, "noop")
        injected = state.extra.get("_injected_hints", [])
        if len(injected) >= self.max_injections:
            return PolicyDecision(self.name, "noop")
        hint = state.recovery_hints.pop(0)
        injected.append(hint)
        state.extra["_injected_hints"] = injected
        return PolicyDecision(self.name, "inject_hint", reason=hint,
                              data={"hint": hint})

    def after_model(self, state, ctx: Dict[str, Any]) -> PolicyDecision:
        if self._has_new_evidence(ctx):
            state.recovery_hints.clear()
        return PolicyDecision(self.name, "noop")

    @staticmethod
    def _has_new_evidence(ctx: Dict[str, Any]) -> bool:
        ctx = ctx or {}
        return ctx.get("status") == "ok" or bool(ctx.get("evidence"))
