"""Tool risk classification (host-agnostic, no DeerFlow imports).

D1: classify a proposed tool call into a risk level so a guardrail layer can
decide allow / deny / require_approval. Purely rules-based + regex; provider
-agnostic. The DeerFlow adapter turns these decisions into guardrail responses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DANGEROUS_PATTERNS: List[str] = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r":\(\)\s*\{.*\}\s*;",
    r"mkfs\b",
    r"dd\s+if=.*of=/dev/sd",
    r"chmod\s+-R\s+777\s+/",
    r">\s*/dev/sd",
    r"shutdown\b",
    r"reboot\b",
    r"curl[^|]*\|\s*(sh|bash)",
    r"wget[^|]*\|\s*(sh|bash)",
    r":\s*\{\s*:\s*\|\s*:",
]

PROTECTED_PATHS: List[str] = [
    "/etc", "/proc", "/boot", "/var/lib", "/root/.ssh",
    "/usr/lib", "/usr/bin",
]

MUTATING_TOOLS: set[str] = {
    "bash", "write_file", "str_replace", "remove", "create_file",
    "write", "exec", "shell", "run_command", "delete", "mkdir", "mv",
}


@dataclass
class ToolRisk:
    level: str = "low"                     # low | medium | high
    is_mutating: bool = False
    protected_path: Optional[str] = None
    requires_user_approval: bool = False
    reason: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


def _match_any(text: str, patterns: List[str]) -> Optional[str]:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return p
    return None


def classify_tool_risk(tool_name: str, args: Any) -> ToolRisk:
    """Classify one tool call into a risk level."""
    args_text = str(args or {}).lower()

    # 1) dangerous command / destructive pattern -> high + approval
    hit = _match_any(args_text, DANGEROUS_PATTERNS)
    if hit:
        return ToolRisk("high", is_mutating=True, requires_user_approval=True,
                        reason=f"dangerous pattern matched: {hit}")

    # 2) protected path (explicit path keys, or any path token in the text)
    protected_pp = None
    if isinstance(args, dict):
        for key in ("path", "cwd", "file", "dir", "target"):
            val = args.get(key)
            if isinstance(val, str):
                for pp in PROTECTED_PATHS:
                    if val.startswith(pp):
                        protected_pp = pp
                        break
                if protected_pp:
                    break
    if not protected_pp:
        for pp in PROTECTED_PATHS:
            # match `/etc`, `/etc/...`, `/etc "`, `/etc'`, `/etc ` etc.
            if re.search(rf"(?<![a-zA-Z0-9_.-]){re.escape(pp)}(?:/|[\s\"']|$)",
                         args_text):
                protected_pp = pp
                break
    if protected_pp:
        return ToolRisk("high", is_mutating=True, protected_path=protected_pp,
                        reason=f"protected path: {protected_pp}")

    # 3) mutating tool -> medium
    if tool_name in MUTATING_TOOLS:
        return ToolRisk("medium", is_mutating=True,
                        reason=f"mutating tool: {tool_name}")

    return ToolRisk("low")
