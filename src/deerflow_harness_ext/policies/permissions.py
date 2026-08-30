"""Permission policy: compile OpenHarness-style permission modes into decisions.

Host-agnostic: consumes a classified ToolRisk and emits an allow/deny/
require_approval decision. The DeerFlow adapter layer turns these into
guardrail provider responses (see deerflow/guardrail_provider).

Modes:
  - default : allow safe reads; require approval for high-risk / approval-worthy calls
  - plan    : strictly read-only; any mutating call is denied
  - approve : every mutating call requires explicit approval
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..core.decisions import PolicyDecision
from ..core.engine import Policy
from ..core.risk import ToolRisk, classify_tool_risk


class PermissionPolicy(Policy):
    """Permission modes: 'default' | 'plan' | 'approve'."""

    name = "permissions"

    def __init__(self, mode: str = "default",
                 protected_paths: Optional[List[str]] = None) -> None:
        self.mode = mode
        self.protected_paths = list(protected_paths) if protected_paths else None

    def after_model(self, state, ctx: Dict[str, Any]) -> PolicyDecision:
        tool = (ctx or {}).get("tool_name")
        args = (ctx or {}).get("tool_args")
        if not tool:
            return PolicyDecision(self.name, "noop")

        risk: ToolRisk = classify_tool_risk(tool, args)

        # caller-supplied extra protected paths override the classifier result.
        # Scan the serialised args (so a path inside a `bash` command counts too).
        if self.protected_paths:
            if isinstance(args, dict):
                args_text = json.dumps(args, sort_keys=True, ensure_ascii=False).lower()
            else:
                args_text = str(args).lower()
            for pp in self.protected_paths:
                if re.search(rf"(?<![a-zA-Z0-9_.-]){re.escape(pp.lower())}(?:/|[\s\"']|$)",
                             args_text):
                    risk = ToolRisk("high", is_mutating=True, protected_path=pp,
                                    reason=f"extra protected path: {pp}")
                    break

        data = {"tool": tool, "risk": risk.level}

        # plan mode is strictly read-only
        if self.mode == "plan" and risk.is_mutating:
            return PolicyDecision(self.name, "deny",
                                  reason=f"plan mode read-only: {risk.reason or tool}",
                                  data=data)

        # protected paths are always denied
        if risk.protected_path:
            return PolicyDecision(self.name, "deny",
                                  reason=f"protected path: {risk.protected_path}",
                                  data=data)

        # approve mode: every mutating call needs approval
        if self.mode == "approve" and risk.is_mutating:
            return PolicyDecision(self.name, "require_approval",
                                  reason=f"approve mode requires approval for mutating: {tool}",
                                  data=data)

        # default mode: high-risk / approval-worthy calls require explicit approval
        if risk.requires_user_approval:
            return PolicyDecision(self.name, "require_approval",
                                  reason=risk.reason or tool, data=data)

        return PolicyDecision(self.name, "allow", data=data)
