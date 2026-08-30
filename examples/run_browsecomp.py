"""Run the harness deep-research agent on a batch of BrowseComp questions.

Envs: APODEX_API_KEY, APODEX_MODEL, SERPER_API_KEY, HTTPS_PROXY.
Usage: python run_browsecomp.py [--n 5] [--offset 0] [--dataset <path>]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browsecomp_agent import answer_question, call_model  # noqa: E402

DEFAULT_DS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "..", "..", "..", "..", "..", "..",
                          "drb_data", "benchmarks", "datasets",
                          "BrowseComp", "standardized_data.jsonl")


def judge(question: str, gt: str, pred: str) -> Tuple[bool, str]:
    """Strict LLM judge: is the model answer correct / equivalent to reference?"""
    if not pred:
        return False, "no answer"
    prompt = (
        "You are a strict judge for the BrowseComp benchmark. "
        "Determine whether the MODEL ANSWER correctly answers the QUESTION and is "
        "equivalent to the REFERENCE ANSWER.\n\n"
        f"QUESTION: {question}\n"
        f"REFERENCE ANSWER: {gt}\n"
        f"MODEL ANSWER: {pred}\n\n"
        'Reply with ONLY JSON: {"correct": true or false, "reason": "one line"}')
    try:
        r = call_model([{"role": "user", "content": prompt}], max_tokens=200)
    except Exception:
        return False, "judge error"
    m = re.search(r'"correct"\s*:\s*(true|false)', r, re.IGNORECASE)
    if not m:
        return False, f"unparseable: {r[:60]}"
    return m.group(1).lower() == "true", r[:120]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--dataset", default=DEFAULT_DS)
    args = ap.parse_args()

    ds = [json.loads(l) for l in io.open(args.dataset, encoding="utf-8")]
    batch = ds[args.offset: args.offset + args.n]
    correct = 0
    for i, item in enumerate(batch):
        q = item["task_question"]
        gt = item["ground_truth"]
        try:
            pred = answer_question(q)
        except Exception as e:
            pred = f"<agent error: {e}>"
        ok, reason = judge(q, gt, pred or "")
        correct += ok
        print(f"[{args.offset + i + 1}] id={item['task_id']} correct={ok}")
        print(f"  Q  : {q[:90]}")
        print(f"  GT : {gt[:90]}")
        print(f"  PRED: {str(pred)[:90]}")
        print(f"  judge: {reason}")
        sys.stdout.flush()
    acc = correct / len(batch) if batch else 0.0
    print(f"\nACC: {correct}/{len(batch)} = {acc:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
