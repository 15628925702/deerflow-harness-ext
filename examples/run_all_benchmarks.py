"""Run each Apodex deep-research benchmark sample SEQUENTIALLY.

Each benchmark is evaluated independently with its own thread pool of `workers`
(default 12) so every benchmark finishes within its own few-hour budget — they are
NOT mixed into one shared pool. Per-benchmark accuracy and elapsed time are printed
as each one completes.

Envs: APODEX_KEYS (comma sep) or APODEX_API_KEY, SERPER_API_KEY, HTTPS_PROXY.
Usage: python run_all_benchmarks.py --sampled <dir> [--workers 12] [--self-consistency 3]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import glob
import io
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browsecomp_agent import answer_question  # noqa: E402
from run_gaia import judge  # noqa: E402


def run_benchmark(name, rows, workers, sc):
    stat = [0, 0]  # [correct, total]

    def solve(item):
        q = item.get("task_question") or item.get("Question") or ""
        gt = item.get("ground_truth") or item.get("Final answer") or ""
        preds = []
        for _ in range(max(1, sc)):
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
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(solve, r) for r in rows]
        for f in concurrent.futures.as_completed(futs):
            if f.result():
                stat[0] += 1
            stat[1] += 1
            done += 1
            if done % 25 == 0 or done == len(rows):
                print(f"    [{name}] {done}/{len(rows)}  acc={stat[0]/done:.1%}", flush=True)
    return stat[0], stat[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sampled", required=True, help="dir containing <Name>.jsonl samples")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--self-consistency", type=int, default=3)
    ap.add_argument("--skip", default="", help="comma list of benchmark names to skip")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.sampled, "*.jsonl")))
    if not files:
        print("no sampled jsonl found"); return 1
    skip = {s.strip() for s in a.skip.split(",") if s.strip()}

    print(f"workers={a.workers}, self-consistency={a.self_consistency}", flush=True)
    results = {}
    for fp in files:
        name = os.path.splitext(os.path.basename(fp))[0]
        if name in skip:
            print(f"skip {name}", flush=True); continue
        rows = [json.loads(l) for l in io.open(fp, encoding="utf-8")]
        print(f"=== {name} 开始 ({len(rows)} 题) ===", flush=True)
        t0 = time.time()
        c, t = run_benchmark(name, rows, a.workers, a.self_consistency)
        el = time.time() - t0
        results[name] = (c, t)
        print(f"=== {name} 完成: {c}/{t} = {c/t:.2%}  用时 {el/60:.1f} 分钟 ===", flush=True)

    print("\n========== 最终汇总 ==========", flush=True)
    gc = gt_ = 0
    for name, (c, t) in results.items():
        print(f"{name:28s} {c:3d}/{t:3d} = {c/t:6.2%}", flush=True)
        gc += c; gt_ += t
    if gt_:
        print(f"{'TOTAL':28s} {gc:3d}/{gt_:3d} = {gc/gt_:6.2%}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
