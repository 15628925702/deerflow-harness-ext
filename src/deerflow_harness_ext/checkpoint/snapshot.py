"""Workspace snapshot: git diff, untracked, HEAD, test evidence (D5)."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorkspaceSnapshot:
    """Point-in-time view of a workspace that can be compared across time."""

    head: Optional[str] = None
    diff: str = ""
    untracked: List[str] = field(default_factory=list)
    test_evidence: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "head": self.head,
            "diff": self.diff,
            "untracked": list(self.untracked),
            "test_evidence": dict(self.test_evidence),
        }

    def apply_to(self, other: "WorkspaceSnapshot") -> bool:
        """True if the workspace changed between `self` and `other`."""
        return (self.head != other.head or self.diff != other.diff
                or self.untracked != other.untracked)


def _git_available(workspace: str) -> bool:
    return os.path.isdir(os.path.join(workspace, ".git"))


def _git(workspace: str, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", workspace, *args],
                           capture_output=True, text=True, timeout=30)
        return r.stdout.rstrip() if r.returncode == 0 else ""
    except Exception:
        return ""


def capture_snapshot(workspace: str, run_git: bool = True) -> WorkspaceSnapshot:
    """Capture a point-in-time snapshot of the workspace.

    With `run_git=True` it reads git HEAD / diff / untracked files; that is
    cheap and non-mutating (a snapshot never changes the workspace).
    """
    snap = WorkspaceSnapshot()
    if run_git and _git_available(workspace):
        snap.head = _git(workspace, "rev-parse", "HEAD")
        snap.diff = _git(workspace, "diff")
        snap.untracked = [
            ln for ln in _git(workspace, "ls-files", "--others", "--exclude-standard").splitlines()
            if ln]
    return snap
