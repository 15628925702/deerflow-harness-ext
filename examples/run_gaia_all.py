"""Run ALL GAIA validation no-attachment questions concurrently (multi-key).

Envs: HF_TOKEN, APODEX_KEYS (comma separated) or APODEX_API_KEY, SERPER_API_KEY, HTTPS_PROXY.
Usage: python run_gaia_all.py [--workers 6] [--limit N]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import sys

import pandas as pd
from huggingface_hub import hf_hub_download

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browsecomp_agent import answer_question  # noqa: E402
from run_gaia import judge  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="limit questions (0 = all)")
    ap.add_argument("--self-consistency", type=int, default=3,
                    help="sample each question N times and majority-vote (default 3)")
    a = ap.parse_args()

    p = hf_hub_download("gaia-benchmark/GAIA", "2023/validation/metadata.parquet",
                        repo_type="dataset", token=os.environ["HF_TOKEN"])
    df = pd.read_parquet(p, engine="fastparquet")
    fn = df["file_name"]
    df = df[fn.isna() | fn.eq("")].reset_index(drop=True)
    if a.limit:
        df = df.iloc[:a.limit]
    rows = [r for _, r in df.iterrows()]
    total = len(rows)
    print(f"总题数: {total}")

    from collections import Counter

    def solve(row):
        q, gt = str(row["Question"]), str(row["Final answer"])
        preds = []
        for _ in range(max(1, a.self_consistency)):
            try:
                p = answer_question(q)
                if p and p.strip():
                    preds.append(p.strip())
            except Exception as e:
                pred = f"<err:{str(e)[:30]}>"
                preds.append(pred)
        pred = Counter(preds).most_common(1)[0][0] if preds else None
        ok, _ = judge(q, gt, pred or "")
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
                print(f"进度: {done}/{total}  当前准确率 {correct}/{done} = {correct/done:.2%}")
                sys.stdout.flush()
    print(f"\n最终 ACC: {correct}/{total} = {correct/total:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
