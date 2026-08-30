"""Failure policy: counts repeated failure fingerprints, emits recovery hints (D2)."""
from __future__ import annotations

from typing import Any, Dict

from ..core.decisions import PolicyDecision
from ..core.engine import Policy
from ..core.failure import fingerprint_tool_outcome


class FailurePolicy(Policy):
    """Detect repeated failures via stable fingerprints.

    Consumes ctx keys: tool_name, error, tool_output, exit_code, status,
    exception_type. Only failed outcomes (error present or status != 'ok')
    are counted. Emits 'hint' once a fingerprint repeats >= max_repeats.
    """

    name = "failure"

    def __init__(self, max_repeats: int = 3, max_unique_failures: int = 20) -> None:
        self.max_repeats = max_repeats
        self.max_unique_failures = max_unique_failures

    def after_model(self, state, ctx: Dict[str, Any]) -> PolicyDecision:
        ctx = ctx or {}
        error = ctx.get("error")
        status = ctx.get("status")
        if error is None and (status is None or status == "ok"):
            return PolicyDecision(self.name, "noop")

        tool = ctx.get("tool_name")
        fp = fingerprint_tool_outcome(
            tool,
            error=error,
            output=ctx.get("tool_output"),
            exit_code=ctx.get("exit_code"),
            exception_type=ctx.get("exception_type"),
        )
        count = state.repeated_failures.get(fp, 0) + 1
        state.repeated_failures[fp] = count
        state.failures.append(fp)
        if len(state.repeated_failures) > self.max_unique_failures:
            oldest = next(iter(state.repeated_failures))
            state.repeated_failures.pop(oldest, None)

        if count >= self.max_repeats:
            hint = f"repeated failure {fp} x{count} (tool={tool})"
            if hint not in state.recovery_hints:
                state.recovery_hints.append(hint)
            return PolicyDecision(self.name, "hint", reason=hint,
                                  data={"fingerprint": fp, "count": count, "tool": tool})
        return PolicyDecision(self.name, "noop")
