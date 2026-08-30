"""Policy decision schema (host-agnostic)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class PolicyDecision:
    """One decision emitted by a policy. `action` is one of:
    noop | compact | hint | deny | allow | require_approval
    """

    policy: str
    action: str
    reason: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "policy": self.policy,
            "action": self.action,
            "reason": self.reason,
            "data": dict(self.data),
        }
