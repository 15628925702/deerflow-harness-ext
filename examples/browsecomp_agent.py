"""Deep-research agent for BrowseComp-style benchmarks.

Reuses the harness strategy layer (failure/stall/recovery/context) plus the
real web tools (Serper search + Jina fetch) to answer a research question.
Each question runs its own ReAct loop; the strategy layer tracks failures,
stalls and recovery hints exactly like the executable-world harness.

Envs: APODEX_API_KEY, APODEX_MODEL, SERPER_API_KEY, HTTPS_PROXY, JINA_API_KEY(opt).
"""
from __future__ import annotations

import itertools
import json
import os
import re
import sys
import threading
import time
import urllib.request
from typing import Any, Dict, List, Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from deerflow_harness_ext.core.engine import HarnessEngine
from deerflow_harness_ext.core.state import HarnessState
from deerflow_harness_ext.policies.context import ContextPolicy
from deerflow_harness_ext.policies.failure import FailurePolicy
from deerflow_harness_ext.policies.recovery import RecoveryPolicy
from deerflow_harness_ext.policies.stall import StallPolicy

try:
    from web_tools import web_search, web_fetch
except ImportError:
    from .web_tools import web_search, web_fetch  # type: ignore

SYSTEM = """\
You are a deep-research agent. Given a question, find the PRECISE answer by
gathering evidence from the web.

Tools:
  - web_search(query) -> list of {title, link, snippet}
  - web_fetch(url) -> readable text of a page

Work: read the question, search, open promising pages, cross-check, then answer.
CRITICAL FORMAT — obey exactly:
  * Reply to EACH turn with EXACTLY ONE JSON object, and nothing else:
        {"tool": "web_search", "query": "..."}
        {"tool": "web_fetch", "url": "..."}
        or, when confident: {"final_answer": "<short precise answer>"}
  * NEVER reply with plain prose, thinking, or explanation. Every single turn is one JSON object.
  * Begin with a web_search about the question.
Rules:
  * Prefer authoritative sources; a precise, sourced answer beats a guess.
  * If you are already confident of the answer from your own knowledge, you may reply
    {"final_answer": ...} immediately without searching.
  * When searching, build the query from the QUESTION's precise named entities, numbers,
    dates, and exact facts — a query with exact details matches far better than a paraphrase.
  * After 1-2 searches, OPEN the most promising result with web_fetch and READ it — snippets are not enough for a precise answer.
  * Aim to answer within about 8 tool calls. Do not search indefinitely.
  * By your last turn you MUST emit {"final_answer": ...}, even a best guess.
"""


def _base() -> str:
    return os.environ.get("APODEX_BASE_URL") or "https://api.apodex.ai/v1"


_keys_pool: list = []
_keys_lock = threading.Lock()
_keys_idx = 0


def _keys() -> list:
    global _keys_pool
    if not _keys_pool:
        arr = [k.strip() for k in (os.environ.get("APODEX_KEYS") or "").split(",") if k.strip()]
        if not arr:
            arr = [os.environ.get("APODEX_API_KEY") or ""]
        _keys_pool = arr
    return _keys_pool


def _next_key() -> str:
    global _keys_idx
    with _keys_lock:
        k = _keys_pool[_keys_idx % len(_keys_pool)]
        _keys_idx += 1
        return k


def _model() -> str:
    return os.environ.get("APODEX_MODEL") or "apodex-1.1"


def call_model(messages: List[Dict[str, str]], max_tokens: int = 1200) -> str:
    keys = _keys()
    if not keys or not keys[0]:
        raise RuntimeError("need APODEX_API_KEY or APODEX_KEYS")
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    handlers = [urllib.request.ProxyHandler({"https": proxy, "http": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    last = None
    for attempt in range(8):  # 429 backoff + key rotation
        key = _next_key()
        body = json.dumps({"model": _model(), "messages": messages,
                           "stream": False, "max_tokens": max_tokens}).encode()
        req = urllib.request.Request(
            _base().rstrip("/") + "/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        try:
            with opener.open(req, timeout=180) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                last = "429"
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except Exception as e:
            last = e
    raise RuntimeError(f"model call failed after retries: {last}")


def _parse_action(text: str) -> Optional[Dict[str, Any]]:
    """Last JSON object that has final_answer, or a tool call {tool, ...}."""
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
        if isinstance(obj, dict) and ("final_answer" in obj or "tool" in obj):
            found = obj
    return found


def answer_question(question: str, max_steps: int = 12) -> Optional[str]:
    """Run one deep-research question, return the final answer (or None)."""
    state = HarnessState()
    eng = HarnessEngine(policies=[
        FailurePolicy(max_repeats=3),
        StallPolicy(threshold=4),
        ContextPolicy(target_fraction=0.9),
        RecoveryPolicy(max_injections=3),
    ])
    tool_desc = "\n".join([
        "  web_search(query)  — search the web",
        "  web_fetch(url)     — read a page",
    ])
    system = SYSTEM + "\nTOOLS\n" + tool_desc
    transcript: List[Dict[str, str]] = [
        {"role": "user", "content": f"QUESTION\n{question}"}]

    for step in range(max_steps):
        if step >= int(max_steps * 0.5):
            transcript.append({"role": "user", "content":
                'CONVERGE NOW: this turn you must emit {"final_answer": ...} based on '
                'what you have, even a best guess. Do NOT search again.'})
        for d in eng.before_model(state, {"thread_state": transcript}):
            if d.action == "inject_hint":
                transcript.append({"role": "user",
                                   "content": "RECOVERY HINT: " + str(d.data.get("hint", ""))})
        try:
            reply = call_model([{"role": "system", "content": system}] + transcript)
        except Exception as e:
            transcript.append({"role": "user", "content": f"model error {e}; retry"})
            continue
        transcript.append({"role": "assistant", "content": reply})

        action = _parse_action(reply)
        if action is None:
            transcript.append({"role": "user", "content":
                               'Reply with JSON {"tool": "...", ...} or {"final_answer": "..."}'})
            continue
        if "final_answer" in action:
            return str(action["final_answer"]).strip()

        tool = action.get("tool")
        if tool == "web_search":
            obs = web_search(str(action.get("query") or action.get("q") or ""))
            status = "ok" if "error" not in obs else "error"
        elif tool == "web_fetch":
            obs = web_fetch(str(action.get("url") or action.get("link") or ""))
            status = "ok" if "error" not in obs else "error"
        else:
            obs = {"error": f"unknown tool {tool}"}
            status = "error"
        eng.after_model(state, {"tool_name": tool, "status": status,
                                "tool_output": obs, "error": obs.get("error")})
        transcript.append({"role": "user", "content":
                           json.dumps(obs, ensure_ascii=False)[:4000]})
    return None
