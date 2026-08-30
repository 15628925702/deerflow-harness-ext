"""mini-SWE-inspired native coding subagent loop (host-agnostic, D4).

The loop is a narrow, linear, evidence-driven cycle: locate -> minimal edit ->
run target test -> summarize. Model and tool execution are injected by the
host, so the loop itself stays host-agnostic and unit-testable.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from .config import CodingConfig
from .prompt import build_system_prompt
from .result import CodingResult

ModelCall = Callable[[List[Dict[str, str]]], str]
Execute = Callable[[str, Dict[str, Any]], Dict[str, Any]]


class CodingAgent:
    """Linear coding loop. `model` and `execute` are injected by the host."""

    def __init__(self, config: CodingConfig, model: ModelCall, execute: Execute) -> None:
        self.config = config
        self.model = model
        self.execute = execute
        self.trajectory: List[Dict[str, Any]] = []

    def run(self, task: str, workspace: str) -> CodingResult:
        system = build_system_prompt(self.config)
        transcript = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"TASK\n{task}\n\nWORKSPACE\n{workspace}"},
        ]
        result = CodingResult()

        for _ in range(self.config.max_turns):
            reply = self._safe_model(transcript)
            transcript.append({"role": "assistant", "content": reply})
            self.trajectory.append({"phase": "model", "content": reply})

            action = self._parse_action(reply)
            if action is None:
                transcript.append({"role": "user", "content":
                                   'No action found. Reply with JSON {"tool": "...", "params": {...}} '
                                   'or {"submit": {...result...}}.'})
                continue
            if "submit" in action:
                return self._finalize(result, action["submit"])

            tool = action.get("tool")
            params = action.get("params") or {}
            if tool not in self.config.tools:
                transcript.append({"role": "user", "content":
                                   f"Tool {tool} not allowed. Allowed: {self.config.tools}."})
                continue

            obs = self._safe_execute(tool, params)
            self.trajectory.append({"phase": "tool", "tool": tool, "obs": obs})
            transcript.append({"role": "user", "content":
                               json.dumps(obs, ensure_ascii=False)[:4000]})

        return result  # never submitted -> not success

    def _safe_model(self, transcript: List[Dict[str, str]]) -> str:
        try:
            return self.model(transcript)
        except Exception as e:                      # model failure != task failure
            return json.dumps({"submit": {"diff_summary": f"model error: {e}",
                                          "success": False}})

    def _safe_execute(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.execute(tool, params) or {}
        except Exception as e:
            return {"error": str(e), "status": "error"}

    @staticmethod
    def _parse_action(text: str) -> Optional[Dict[str, Any]]:
        """Extract the LAST well-formed JSON object with 'tool' or 'submit'."""
        if not text:
            return None
        for m in re.finditer(r"\{", text):
            depth = 0
            end = None
            for i in range(m.start(), len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end is None:
                continue
            try:
                obj = json.loads(text[m.start():end])
            except ValueError:
                continue
            if isinstance(obj, dict) and ("tool" in obj or "submit" in obj):
                return obj
        return None

    @staticmethod
    def _finalize(result: CodingResult, submit: Any) -> CodingResult:
        if isinstance(submit, dict):
            result.changed_files = list(submit.get("changed_files") or [])
            result.tests_run = list(submit.get("tests_run") or [])
            result.test_results = dict(submit.get("test_results") or {})
            result.remaining_risks = list(submit.get("remaining_risks") or [])
            result.diff_summary = str(submit.get("diff_summary") or "")
            result.success = bool(submit.get("success"))
        return result
