"""Read-only review: evaluate a coding result against completion criteria (D5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

_PASS_MARKERS = {"pass", "passed", "ok", "true", "0", "success", "succeeded",
                 "0 failures", "0 failed"}


@dataclass
class ReviewFinding:
    severity: str            # error | warning | info
    message: str


@dataclass
class ReviewResult:
    passed: bool = False
    findings: List[ReviewFinding] = field(default_factory=list)
    summary: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "findings": [{"severity": f.severity, "message": f.message}
                         for f in self.findings],
            "summary": self.summary,
        }


def review_coding_result(result) -> ReviewResult:
    """Verify a CodingResult meets completion criteria.

    Host-agnostic and read-only (never touches the workspace). Errors are
    blocking; warnings are advisory.
    """
    r = ReviewResult()
    if not result.success:
        r.findings.append(ReviewFinding("error", "agent did not report success"))
    if not result.changed_files:
        r.findings.append(ReviewFinding("error", "no changed files"))

    if result.test_results:
        for name, res in result.test_results.items():
            if str(res).strip().lower() not in _PASS_MARKERS:
                r.findings.append(
                    ReviewFinding("warning", f"test {name} not clearly passing: {res}"))
    elif result.tests_run:
        r.findings.append(
            ReviewFinding("warning", "tests_run present but no test_results"))
    else:
        r.findings.append(
            ReviewFinding("warning", "no tests run (violates test-driven policy)"))

    r.passed = not any(f.severity == "error" for f in r.findings)
    r.summary = "pass" if r.passed else "; ".join(
        f.message for f in r.findings if f.severity == "error")
    return r
