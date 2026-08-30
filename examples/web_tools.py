"""Real web tools for the harness (web search via Serper).

An official-capable harness needs web tools for deep-research style tasks
(the executable-world interface has no web, but TRACES / deep-research
benchmarks do). This adds a real `web_search` tool backed by Serper.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List

SERPER_URL = "https://google.serper.dev/search"


def _proxy_handlers() -> List[urllib.request.BaseHandler]:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        return [urllib.request.ProxyHandler({"https": proxy, "http": proxy})]
    return []


def web_search(query: str, num: int = 5) -> Dict[str, Any]:
    """Run a Google search via Serper and return the organic results."""
    key = os.environ.get("SERPER_API_KEY") or os.environ.get("SERPER_KEY") or ""
    if not key:
        return {"error": "no SERPER_API_KEY set"}
    body = json.dumps({"q": query, "num": int(num)}).encode("utf-8")
    req = urllib.request.Request(
        SERPER_URL, data=body,
        headers={"X-API-KEY": key, "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(*_proxy_handlers()).open(req, timeout=30) as r:
            data = json.loads(r.read())
    except Exception as exc:                       # a failed search is not fatal
        return {"error": str(exc)}
    results = []
    for item in data.get("organic", [])[:int(num)]:
        results.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "snippet": item.get("snippet"),
        })
    return {"results": results}


# Alias used by harnesses that expect a `search` tool name.
search = web_search


def web_fetch(url: str) -> Dict[str, Any]:
    """Fetch a URL and return its readable text via Jina Reader.

    Jina's free tier works without a key (rate-limited); if a JINA_API_KEY is
    set it is used for higher limits.
    """
    target = "https://r.jina.ai/" + url
    headers = {}
    key = os.environ.get("JINA_API_KEY") or ""
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(target, headers=headers)
    try:
        with urllib.request.build_opener(*_proxy_handlers()).open(req, timeout=40) as r:
            return {"text": r.read().decode("utf-8", errors="replace")[:20000]}
    except Exception as exc:
        return {"error": str(exc)}


# Alias used by harnesses that expect a `fetch` tool name.
fetch = web_fetch
