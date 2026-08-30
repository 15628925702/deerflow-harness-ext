"""Dry-run ledger: an explicit, auditable record of policy decisions.

The HarnessEngine already keeps an in-memory ledger; DryRunLedger adds an
append-only serialized copy (e.g. for dry-run / A/B / audit without a DB).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DryRunLedger:
    entries: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, decision) -> None:
        self.entries.append(decision.as_dict() if hasattr(decision, "as_dict") else dict(decision))

    def extend(self, decisions) -> None:
        for d in decisions:
            self.add(d)

    def dump(self) -> List[Dict[str, Any]]:
        return list(self.entries)
