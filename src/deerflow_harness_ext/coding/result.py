"""Coding subagent result schema (D4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CodingResult:
    """Structured result a coding subagent returns to the lead agent."""

    changed_files: List[str] = field(default_factory=list)
    tests_run: List[str] = field(default_factory=list)
    test_results: Dict[str, Any] = field(default_factory=dict)
    remaining_risks: List[str] = field(default_factory=list)
    diff_summary: str = ""
    success: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "changed_files": list(self.changed_files),
            "tests_run": list(self.tests_run),
            "test_results": dict(self.test_results),
            "remaining_risks": list(self.remaining_risks),
            "diff_summary": self.diff_summary,
            "success": self.success,
        }
