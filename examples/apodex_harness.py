"""End-to-end harness demo: strategy layer + apodex model driving an
executable-world task (Apodex TRACES example-kit interface).

This is a reference implementation of how the host-agnostic policy layer
(wrapped as a DeerFlow-style middleware loop) is combined with a concrete
model (apodex, OpenAI-compatible) to drive an executable-world environment.

Run against the example kit (`executable-world-examples`), from its directory:

    export APODEX_API_KEY=sk-...                 # apodex key
    export APODEX_MODEL=apodex-1.1-mini          # free model
    export HTTPS_PROXY=http://127.0.0.1:7897     # needed if apodex blocks your region
    PYTHONPATH=<repo>/src:<repo>/examples python run_task.py \
        --task verify_solutions --agent apodex_harness:solve

`solve(task, ep)` is the `--agent module:function` entry the kit calls.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional

# Robustness: the example-kit observes may contain non-ASCII bytes; never let a
# console encoding error kill a run.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from deerflow_harness_ext.core.engine import HarnessEngine
from deerflow_harness_ext.core.state import HarnessState
from deerflow_harness_ext.policies.context import ContextPolicy
from deerflow_harness_ext.policies.failure import FailurePolicy
from deerflow_harness_ext.policies.permissions import PermissionPolicy
from deerflow_harness_ext.policies.recovery import RecoveryPolicy
from deerflow_harness_ext.policies.stall import StallPolicy

SYSTEM = """\
You are operating inside a sandboxed environment. You cannot see it directly. You
act only through the actions listed below, and every action spends from a finite
budget shown to you after each step.

Reply with ONE action as JSON and nothing else:

    {"action": "<name>", "params": {...}}

Rules that decide whether you do well here:
  * Spend free actions before paid ones.
  * Prefer the action that separates several possibilities at once.
  * An error reply is not fatal. Read it, fix the call, continue.
  * You MUST finish by submitting a concrete, executable result. Observation alone
    scores nothing.
  * Detect decoys concretely:
      - MIRROR: fetch docs from each source and record their content_hash; a source whose
        hashes repeat hashes already seen in another source is a decoy (zero unique value).
      - HONEYPOT: re-sample a source twice; if it yields fresh items every time (never
        repeats), it is a decoy generator — exclude it.
      - CONTAMINATION: landing too much junk/spam can trip a hard gate that zeroes the
        whole plan. Keep landed junk below the threshold.
      - MISLEADING FIELDS: verify or declare anything you rely on.
    The quality of what you submit matters, not just having submitted something.
  * Budget and steps are finite. Do not spend all your turns exploring — land a
    real submission early, then refine if the environment gives feedback.
"""

SUBMIT_REMINDER = (
    "REMINDER: you are well into the episode. You MUST now submit a concrete, "
    "executable result. Exploring or analyzing without submitting scores zero."
)


def _base() -> str:
    return os.environ.get("APODEX_BASE_URL") or "https://api.apodex.ai/v1"


def _key() -> str:
    return os.environ.get("APODEX_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""


def _model() -> str:
    return os.environ.get("APODEX_MODEL") or os.environ.get("OPENAI_MODEL") or "apodex-1.1-mini"


def call_model(system: str, transcript: List[Dict[str, str]], max_tokens: Optional[int] = None) -> str:
    """One key only. On 429 wait and retry the same key — never rotate."""
    key = _key()
    if not key:
        raise RuntimeError("need APODEX_API_KEY")
    if max_tokens is None:
        max_tokens = int(os.environ.get("APODEX_MAX_TOKENS") or 1024)
    body = json.dumps({
        "model": _model(),
        "messages": [{"role": "system", "content": system}] + transcript,
        "stream": False,
        "max_tokens": int(max_tokens),
    }).encode()
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    handlers = [urllib.request.ProxyHandler({"https": proxy, "http": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    last = None
    for attempt in range(8):
        req = urllib.request.Request(
            _base().rstrip("/") + "/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        try:
            with opener.open(req, timeout=300 if int(max_tokens) > 2048 else 180) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                time.sleep(min(60.0, 2.0 ** attempt))
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(min(30.0, 1.5 * (attempt + 1)))
    raise RuntimeError(f"model call failed after retries: {last}")


def _describe_actions(task) -> str:
    return "\n".join(f"  {n}  (cost {s.cost})  {s.doc}" for n, s in task.actions().items())


def _extract_action(text: str) -> Optional[Dict[str, Any]]:
    """Extract the LAST well-formed JSON object that has an 'action' key."""
    if not text:
        return None
    found = None
    for m in re.finditer(r"\{", text):
        depth, end = 0, None
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
        if isinstance(obj, dict) and isinstance(obj.get("action"), str):
            found = obj
    return found


def solve(task, ep, *, max_steps: int = 40, verbose: bool = True):
    """Task-agnostic loop wrapped with the harness strategy layer."""
    state = HarnessState()
    eng = HarnessEngine(policies=[
        FailurePolicy(max_repeats=3),
        StallPolicy(threshold=4),
        PermissionPolicy(mode="default"),
        ContextPolicy(target_fraction=0.9),
        RecoveryPolicy(max_injections=3),
    ])
    system = SYSTEM + "\nACTIONS AVAILABLE\n" + _describe_actions(task)
    transcript: List[Dict[str, str]] = [
        {"role": "user", "content": f"TASK BRIEF\n{task.brief}\n\nTake your first action."}]

    reminded = False
    for step in range(max_steps):
        if ep.done:
            break
        # step-based submission reminder (early fallback; budget-aware below)
        if step >= int(max_steps * 0.4) and not reminded:
            transcript.append({"role": "user", "content": SUBMIT_REMINDER})
            reminded = True

        # strategy: before-model decisions (e.g. inject recovery hints)
        for d in eng.before_model(state, {"thread_state": transcript}):
            if d.action == "inject_hint":
                transcript.append({"role": "user",
                                   "content": "RECOVERY HINT: " + str(d.data.get("hint", ""))})

        try:
            reply = call_model(system, transcript)
        except Exception as e:
            transcript.append({"role": "user", "content": f"Your last call failed ({e}). Retry."})
            continue
        transcript.append({"role": "assistant", "content": reply})

        chosen = _extract_action(reply)
        if chosen is None:
            transcript.append({"role": "user", "content":
                               'Reply with exactly {"action": "...", "params": {...}}.'})
            continue

        env = ep.act(chosen["action"], chosen.get("params") or {})
        if verbose:
            print(f"  [{step + 1}] {chosen['action']:18} {env['status']}"
                  f"  budget={env.get('budget_remaining')}")
        # strategy: after-model decisions (failure/stall/permissions tracking)
        eng.after_model(state, {
            "tool_name": chosen["action"],
            "status": env.get("status"),
            "tool_output": env.get("observation"),
            "error": env.get("error"),
        })
        transcript.append({"role": "user", "content": json.dumps(
            {k: v for k, v in env.items() if k != "protocol"},
            ensure_ascii=False)[:6000]})
        # budget-aware submission reminder: env budget near zero -> submit now
        budget = env.get("budget_remaining")
        if isinstance(budget, dict) and budget and not reminded:
            try:
                if min(int(v) for v in budget.values() if isinstance(v, int)) <= 3:
                    transcript.append({"role": "user", "content": SUBMIT_REMINDER})
                    reminded = True
            except (TypeError, ValueError):
                pass

    if verbose and not ep.done:
        print("  never submitted — that scores nothing")
    return ep.result
