"""Config loader for the harness extension (YAML via lazy import)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def load_config(path: str) -> Dict[str, Any]:
    """Load a harness-ext config yaml into a dict."""
    import yaml  # lazy: pyyaml is an optional deerflow extra

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def policies_from_config(cfg: Dict[str, Any]) -> list:
    """Instantiate the policy list declared under cfg['policies']."""
    from ..policies.context import ContextPolicy
    from ..policies.failure import FailurePolicy
    from ..policies.permissions import PermissionPolicy
    from ..policies.recovery import RecoveryPolicy
    from ..policies.stall import StallPolicy

    registry = {"context": ContextPolicy, "failure": FailurePolicy,
                "permissions": PermissionPolicy, "recovery": RecoveryPolicy,
                "stall": StallPolicy}
    out = []
    for name, opts in (cfg.get("policies") or {}).items():
        cls = registry.get(name)
        if cls is not None:
            out.append(cls(**(opts or {})))
    return out
