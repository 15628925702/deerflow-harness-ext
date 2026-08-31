"""DiscoveryWorld Easy scenarios driven by the same apodex_harness.call_model.

Single-key, sequential. Writes scorecard JSON to --out.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Dict, Optional

# harness/examples on path
from apodex_harness import call_model, _extract_action


def _patch_pygame_win32_fonts() -> None:
    """pygame 2.6 + Python 3.13 on Windows: font registry can yield DWORD, crash SysFont."""
    import os
    try:
        import pygame.sysfont as sysfont
    except Exception:
        return
    real = getattr(sysfont, "splitext", None)
    if real is None:
        from os.path import splitext as real  # type: ignore
    def safe_splitext(p):
        if not isinstance(p, (str, bytes, os.PathLike)):
            return ("", "")
        return real(p)
    sysfont.splitext = safe_splitext  # type: ignore[attr-defined]


def _json_action(text: str) -> Optional[Dict[str, Any]]:
    obj = _extract_action(text)
    if obj:
        return obj
    m = re.search(r"\{[\s\S]*\}", text or "")
    if not m:
        return None
    try:
        o = json.loads(m.group(0))
        return o if isinstance(o, dict) else None
    except ValueError:
        return None


def run_scenario(scenario: str, difficulty: str, seed: int, max_steps: int, out_dir: str) -> Dict[str, Any]:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    _patch_pygame_win32_fonts()
    from discoveryworld.DiscoveryWorldAPI import DiscoveryWorldAPI

    api = DiscoveryWorldAPI(threadID=0)
    ok = api.loadScenario(scenarioName=scenario, difficultyStr=difficulty,
                          randomSeed=seed, numUserAgents=1)
    if not ok:
        return {"ok": False, "error": f"loadScenario failed: {scenario} {difficulty} seed={seed}"}

    last: Any = None
    for step in range(max_steps):
        obs = api.getAgentObservation(agentIdx=0)
        in_dialog = False
        try:
            in_dialog = bool(api.isAgentInDialog(agentIdx=0))
        except Exception:
            in_dialog = False
        if in_dialog:
            prompt = (
                "You are in a dialog. Reply with ONE JSON object choosing an option.\n"
                f"DIALOG:\n{json.dumps((obs.get('ui') or {}).get('dialog_box'), ensure_ascii=False)[:3000]}\n"
                'Reply only JSON like {"chosen_dialog_option_int": 1}.'
            )
        else:
            prompt = (
                "You are in a scientific discovery environment. Reply with ONE JSON action.\n"
                f"TASK:\n{json.dumps(obs.get('ui', {}).get('taskProgress', []), ensure_ascii=False)[:3000]}\n"
                f"KNOWN ACTIONS:\n{json.dumps(api.listKnownActions(limited=False), ensure_ascii=False)[:2500]}\n"
                f"TELEPORT:\n{json.dumps(api.listTeleportLocationsDict(), ensure_ascii=False)[:1500]}\n"
                f"LAST RESULT:\n{json.dumps(last, ensure_ascii=False)[:2000]}\n"
                'Reply only JSON like {"action": "USE", "arg1": uuid, "arg2": uuid}.'
            )
        reply = call_model(
            "Reply with exactly one JSON object and nothing else.",
            [{"role": "user", "content": prompt}],
        )
        action = _json_action(reply) or (
            {"chosen_dialog_option_int": 1} if in_dialog else {"action": "WAIT"}
        )
        last = api.performAgentAction(agentIdx=0, actionJSON=action)
        print(f"  [dw {step+1}/{max_steps}] {action.get('action')}", flush=True)
        dl = os.environ.get("EVAL_DEADLINE_TS") or ""
        if dl:
            try:
                if time.time() >= float(dl):
                    print("  [dw] time budget hit mid-scenario", flush=True)
                    break
            except ValueError:
                pass
        if api.areTasksComplete():
            break

    card = api.getTaskScorecard()
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "scorecard.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2, ensure_ascii=False, default=str)
    return {"ok": True, "scorecard": card, "path": path}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--difficulty", default="Easy")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r = run_scenario(a.scenario, a.difficulty, a.seed, a.max_steps, a.out)
    json.dump({k: v for k, v in r.items() if k != "scorecard"}, sys.stdout, indent=2)
    print()
    raise SystemExit(0 if r.get("ok") else 1)
