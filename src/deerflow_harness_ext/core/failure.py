"""Failure fingerprinting (host-agnostic, D2).

Turning raw tool outcomes / errors into *stable, comparable* fingerprints so a
policy can count repeated failures without caring about noise (timestamps,
addresses, pids, token counts). The fingerprint is the only input the
FailurePolicy consumes; where it comes from (ToolMessage, receipt, sandbox
diff) is the host adapter's job — this module stays pure.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

# Patterns that make an otherwise-identical failure look different across runs.
# We strip these before fingerprinting so the same failure maps to one key.
_NOISE_PATTERNS: list[str] = [
    r"timestamp[=:\s]+[\w\-\s:,\.]+",
    r"\[\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?[^\]]*\]",
    r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\b",
    r"0x[0-9a-fA-F]{6,}",
    r"\bpid\s*[:=]?\s*\d+",
    r"\btoken\(s?\)\b",
    r"in \d+(\.\d+)?(ms|s|us)\b",
    r"file\([\w:\\.\-]+\)",
]


def normalize_text(text: str) -> str:
    """Lowercase, strip noise, collapse whitespace — the fingerprint basis."""
    t = text or ""
    for pat in _NOISE_PATTERNS:
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def _hex(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def fingerprint_tool_outcome(
    tool_name: str,
    *,
    error: Optional[Any] = None,
    output: Optional[Any] = None,
    exit_code: Optional[int] = None,
    exception_type: Optional[str] = None,
) -> str:
    """Compute a stable fingerprint for one tool outcome.

    Priority: explicit error > output text > non-zero exit code > ok.
    `error` may be an exception object or a string; `output` may be a string,
    dict, or list (JSON-serialised then normalised).
    """
    if error is not None:
        err_text = str(error)
        exc = exception_type or (type(error).__name__ if not isinstance(error, str) else None)
        key = f"err:{exc or 'unknown'}:{normalize_text(err_text)}"
    elif output is not None:
        if isinstance(output, (dict, list)):
            try:
                out_text = json.dumps(output, sort_keys=True, ensure_ascii=False)
            except TypeError:
                out_text = str(output)
        else:
            out_text = str(output)
        key = f"out:{tool_name}:{normalize_text(out_text)[:240]}"
    elif exit_code is not None and exit_code != 0:
        key = f"exit:{tool_name}:{exit_code}"
    else:
        key = f"ok:{tool_name}"
    return _hex(key)
