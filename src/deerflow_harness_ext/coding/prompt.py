"""Build coding subagent system prompts (D4)."""
from __future__ import annotations

from .config import CodingConfig


def build_system_prompt(cfg: CodingConfig) -> str:
    """Construct the coding subagent's system prompt.

    Encodes the mini-SWE-inspired principles: narrow evidence-driven linear
    loop, test-driven, no web, structured final JSON.
    """
    if cfg.system_prompt:
        return cfg.system_prompt

    tool_list = ", ".join(cfg.tools) if cfg.tools else "(none)"
    lines = [
        "You are a coding subagent working on a repository.",
        "Work in a narrow, evidence-driven, linear loop: "
        "locate -> minimal edit -> run the target test -> expand -> summarize.",
        f"Available tools: {tool_list}.",
    ]
    if cfg.forbid_web:
        lines.append("Web / network / MCP tools are forbidden.")
    if cfg.test_driven:
        lines.append(
            "Always test your change before returning; report test results as evidence.")
    lines.append(
        "Return your final answer as a JSON object with keys: "
        "changed_files, tests_run, test_results, remaining_risks, diff_summary, success.")
    return "\n".join(lines)
