"""Checkpoint store: keeps a history of workspace snapshots (D5).

Separates *workspace* checkpoints (git diff / untracked / test evidence) from
DeerFlow's LangGraph conversation checkpointer. The conversation replay is NOT
a code rollback; this store is the code-level audit/rollback record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .snapshot import WorkspaceSnapshot, capture_snapshot


@dataclass
class CheckpointStore:
    """Append-only history of workspace snapshots for one workspace."""

    workspace: str
    history: List[WorkspaceSnapshot] = field(default_factory=list)
    _default_run_git: bool = True

    def record(self, test_evidence: Optional[Dict[str, Any]] = None) -> WorkspaceSnapshot:
        snap = capture_snapshot(self.workspace, run_git=self._default_run_git)
        snap.test_evidence = dict(test_evidence or {})
        self.history.append(snap)
        return snap

    def changed_since(self, back: int = 1) -> bool:
        """True if the workspace changed between the snapshot `back` ago and the last."""
        if len(self.history) < 2:
            return False
        idx = len(self.history) - 1 - back
        if idx < 0:
            return False
        return self.history[idx].apply_to(self.history[-1])

    def latest(self) -> Optional[WorkspaceSnapshot]:
        return self.history[-1] if self.history else None

    def as_records(self) -> List[Dict[str, Any]]:
        return [s.as_dict() for s in self.history]
