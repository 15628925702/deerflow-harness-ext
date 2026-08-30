"""Coding subagent configuration (D4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

DEFAULT_CODING_TOOLS: List[str] = [
    "bash", "read_file", "write_file", "str_replace", "grep", "glob",
]


@dataclass
class CodingConfig:
    """Configuration for the coding subagent.

    Defaults follow the engineering report: a narrow tool set, test-driven,
    web/MCP forbidden by default.
    """

    tools: List[str] = field(default_factory=lambda: list(DEFAULT_CODING_TOOLS))
    max_turns: int = 30
    test_driven: bool = True
    forbid_web: bool = True
    system_prompt: str = ""            # empty -> build_system_prompt() default
    timeout_seconds: int = 600
