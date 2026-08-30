"""Bridge a sandbox's execute_command to a mini-SWE-style Environment (D6)."""
from __future__ import annotations

import hashlib
import os
import shlex
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ActionRecord:
    command: str
    cwd: str
    timeout: float
    output_digest: str
    returncode: int
    started_at_diff: str = ""          # workspace diff digest before the action

    def as_dict(self) -> Dict[str, Any]:
        return {"command": self.command, "cwd": self.cwd, "timeout": self.timeout,
                "output_digest": self.output_digest, "returncode": self.returncode,
                "started_at_diff": self.started_at_diff}


class SandboxEnvironment:
    """mini-SWE Environment.execute(action, cwd) shape, backed by a sandbox.

    `sandbox` must expose ``execute_command(command, env=None, timeout=...)``
    returning output text. Paths are resolved and confined to the workspace
    root (``cwd`` may not escape it). Every action is recorded with a timeout,
    an output digest and the workspace diff digest for audit/telemetry.
    """

    def __init__(self, sandbox: Any, workspace: str, timeout: float = 30.0) -> None:
        self.sandbox = sandbox
        self.workspace = os.path.abspath(workspace)
        self.timeout = float(timeout)
        self.records: List[ActionRecord] = []

    def _resolve_cwd(self, cwd: str = "") -> str:
        base = os.path.join(self.workspace, cwd or "")
        resolved = os.path.abspath(base)
        if not (resolved == self.workspace or resolved.startswith(self.workspace + os.sep)):
            raise ValueError(f"cwd escapes workspace: {resolved}")
        return resolved

    def execute(self, action: Dict[str, Any], cwd: str = "",
                env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        command = action["command"]
        workdir = self._resolve_cwd(cwd)
        wrapped = f"cd {shlex.quote(workdir)} && {command}"
        diff_before = self._diff_digest()
        try:
            # env injected via the sandbox call, never concatenated into the command
            output = self.sandbox.execute_command(wrapped, env=env, timeout=self.timeout)
            returncode = 0
        except Exception as exc:
            output = str(exc)
            returncode = 1
        rec = ActionRecord(
            command=command, cwd=workdir, timeout=self.timeout,
            output_digest=hashlib.sha256(str(output).encode("utf-8", "replace")).hexdigest()[:16],
            returncode=returncode, started_at_diff=diff_before)
        self.records.append(rec)
        return {"output": output, "returncode": returncode, "record": rec.as_dict()}

    def _diff_digest(self) -> str:
        dig = hashlib.sha256()
        for r in self.records:
            dig.update(f"{r.command}{r.cwd}{r.output_digest}".encode())
        return dig.hexdigest()[:16]
