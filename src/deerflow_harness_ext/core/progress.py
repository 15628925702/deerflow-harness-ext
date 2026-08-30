"""No-progress tracking (host-agnostic, D2).

Detects when an agent loop stops making progress — e.g. it keeps emitting the
same tool output or the same action. Bounded memory (only the last N distinct
outputs are kept) so it can run for very long horizons.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class NoProgressTracker:
    """Tracks repeated identical outputs to detect a stall."""

    stall_threshold: int = 5
    max_distinct: int = 20
    _last: Optional[str] = None
    _streak: int = 0
    _history: List[str] = field(default_factory=list)

    def record(self, output: Optional[str]) -> int:
        """Record one tool output; returns the current consecutive-repeat streak.

        A ``None`` output counts as no evidence (streak resets to 0). A repeated
        identical output increments the streak; any change resets it.
        """
        if output is None:
            self._streak = 0
            self._last = None
            return 0
        if not isinstance(output, str):
            try:
                norm = json.dumps(output, sort_keys=True, ensure_ascii=False)
            except TypeError:
                norm = str(output)
        else:
            norm = output
        norm = norm.strip()
        if self._last is not None and norm == self._last:
            self._streak += 1
        else:
            self._last = norm
            if norm not in self._history:
                self._history.append(norm)
                if len(self._history) > self.max_distinct:
                    self._history = self._history[-self.max_distinct:]
            self._streak = 0
        return self._streak

    @property
    def stalled(self) -> bool:
        """True once the same output has repeated >= stall_threshold times."""
        return self._streak >= self.stall_threshold

    @property
    def streak(self) -> int:
        return self._streak
