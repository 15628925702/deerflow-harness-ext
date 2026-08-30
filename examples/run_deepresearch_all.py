"""Run ANY deep-research benchmark (standardized_data.jsonl) with the harness agent.

Reuses browsecomp_agent (multi-key + 429 retry) and the normalized judge.
Supports self-consistency majority voting + concurrency.

Envs: APODEX_KEYS (or APODEX_API_KEY), SERPER_API_KEY, HTTPS_PROXY.
Usage: python run_deepresearch_all.py --dataset <path.jsonl> [--workers 8] [--self-consistency 3]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browsecomp_agent import answer_question  # noqa: E402
from run_gaia import judge  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="path to standardized_data.jsonl")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--self-consistency", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    rows = [json.loads(l) for l in io.open(a.dataset, encoding="utf-8")]
    if a.limit:
        rows = rows[:a.limit]
    total = len(rows)
    print(f"[{os.path.basename(a.dataset)}] 总题数: {total}")

    def solve(item):
        q = item.get("task_question") or item.get("Question") or ""
        gt = item.get("ground_truth") or item.get("Final answer") or ""
        preds = []
        for _ in range(max(1, a.self_consistency)):
            try:
                p = answer_question(str(q))
                if p and p.strip():
                    preds.append(p.strip())
            except Exception:
                pass
        pred = Counter(preds).most_common(1)[0][0] if preds else None
        ok, _ = judge(str(q), str(gt), pred or "")
        return ok

    done = 0
    correct = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futures = [ex.submit(solve, r) for r in rows]
        for f in concurrent.futures.as_completed(futures):
            done += 1
            if f.result():
                correct += 1
            if done % 10 == 0 or done == total:
                print(f"进度: {done}/{total}  准确率 {correct}/{done} = {correct/done:.2%}")
                sys.stdout.flush()
    print(f"\n[{os.path.basename(a.dataset)}] 最终 ACC: {correct}/{total} = {correct/total:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
