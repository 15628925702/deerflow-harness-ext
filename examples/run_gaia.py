"""Run GAIA validation with the harness deep-research agent.

Envs: HF_TOKEN, APODEX_API_KEY, APODEX_MODEL, SERPER_API_KEY, HTTPS_PROXY.
Usage: python run_gaia.py [--n 10] [--offset 0] [--with-files]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import pandas as pd
from huggingface_hub import hf_hub_download

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browsecomp_agent import answer_question, call_model  # noqa: E402


def judge(question: str, gt: str, pred: str):
    if not pred:
        return False, "no answer"
    # GAIA answers are often precise values: exact / containment match first.
    p = str(pred).strip().lower()
    g = str(gt).strip().lower()
    # normalize whitespace / punctuation separators ("3.1.3.1;1.11.1.7" == "3.1.3.1; 1.11.1.7")
    np = re.sub(r"[\s,;:]+", " ", p).strip()
    ng = re.sub(r"[\s,;:]+", " ", g).strip()
    if p and (p == g or np == ng):
        return True, "exact/norm match"
    # numeric: compare the first number extracted from each side
    def nums(s):
        return re.findall(r"\d+\.?\d*", s)
    pn, gn = nums(p), nums(g)
    if gn and pn and pn[0] == gn[0]:
        return True, f"numeric match ({pn[0]})"
    # containment only when both sides are long enough (avoid '17 in 17000')
    if p and len(p) >= 4 and len(g) >= 4 and (p in g or g in p):
        return True, "containment match"
    prompt = ("You are a strict judge for the GAIA benchmark. Is the MODEL ANSWER "
              "correct / equivalent to the REFERENCE?\n\n"
              f"QUESTION: {question}\nREFERENCE: {gt}\nMODEL ANSWER: {pred}\n\n"
              'Reply ONLY JSON {"correct": true/false, "reason": "one line"}')
    try:
        r = call_model([{"role": "user", "content": prompt}], max_tokens=200)
    except Exception:
        return False, "judge error"
    m = re.search(r'"correct"\s*:\s*(true|false)', r, re.IGNORECASE)
    return (m is not None and m.group(1).lower() == "true"), r[:100]


def self_verify(question: str, preds) -> str:
    """best-of-N: ask the model to pick the most correct candidate answer."""
    if len(preds) <= 1:
        return preds[0] if preds else ""
    body = "\n".join(f"[{i}] {p[:200]}" for i, p in enumerate(preds))
    prompt = (f"QUESTION: {question}\n\nCandidate answers:\n{body}\n\n"
              "Which candidate is the most correct, precise answer to the question? "
              "Reply ONLY with the index number (an integer).")
    try:
        r = call_model([{"role": "user", "content": prompt}], max_tokens=50)
        m = re.search(r"\d+", r)
        if m:
            idx = int(m.group(0))
            if 0 <= idx < len(preds):
                return preds[idx]
    except Exception:
        pass
    return preds[0]


def cluster_vote(question: str, preds) -> str:
    """Semantic-cluster vote: ask the model to group equivalent answers, pick the largest cluster."""
    if len(preds) <= 1:
        return preds[0] if preds else ""
    body = "\n".join(f"[{i}] {p[:150]}" for i, p in enumerate(preds))
    prompt = (f"QUESTION: {question}\n\nCandidate answers:\n{body}\n\n"
              "Group the candidate answers into clusters of EQUIVALENT meaning. "
              'Reply ONLY JSON like {"clusters": [[0,2],[1]]} — indices of answers that mean the same.')
    try:
        r = call_model([{"role": "user", "content": prompt}], max_tokens=200)
        import re as _re
        m = _re.search(r"\{.*\}", r, _re.S)
        clusters = None
        if m:
            import json as _json
            try:
                clusters = _json.loads(m.group(0)).get("clusters")
            except Exception:
                clusters = None
        if clusters:
            from collections import Counter
            best = max(clusters, key=len, default=None)
            if best:
                idx = Counter(best).most_common(1)[0][0]
                if 0 <= idx < len(preds):
                    return preds[idx]
    except Exception:
        pass
    from collections import Counter
    return Counter(preds).most_common(1)[0][0]


def weighted_vote(preds) -> str:
    """Frequency-weighted vote. (True logprob weighting needs API logprobs; without
    them, frequency weighting == majority.)"""
    from collections import Counter
    if not preds:
        return ""
    return Counter(preds).most_common(1)[0][0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--with-files", action="store_true",
                    help="include questions that need an attachment file")
    ap.add_argument("--self-consistency", type=int, default=1,
                    help="run each question N times and take the majority answer")
    ap.add_argument("--self-verify", action="store_true",
                    help="after sampling, ask the model to pick the best candidate (best-of-N)")
    ap.add_argument("--cluster", action="store_true",
                    help="semantic-cluster vote (LLM groups equivalent answers)")
    ap.add_argument("--weighted", action="store_true",
                    help="frequency-weighted vote (== majority without logprobs)")
    ap.add_argument("--dynamic", action="store_true",
                    help="stop sampling early once the majority is stable")
    a = ap.parse_args()

    p = hf_hub_download("gaia-benchmark/GAIA", "2023/validation/metadata.parquet",
                        repo_type="dataset", token=os.environ["HF_TOKEN"])
    df = pd.read_parquet(p, engine="fastparquet")
    if not a.with_files:
        fn = df["file_name"]
        df = df[fn.isna() | fn.eq("")]
    df = df.reset_index(drop=True)
    batch = df.iloc[a.offset:a.offset + a.n]

    from collections import Counter
    correct = 0
    for i, row in batch.iterrows():
        q = str(row["Question"])
        gt = str(row["Final answer"])
        preds = []
        for r in range(max(1, a.self_consistency)):
            try:
                p = answer_question(q)
                if p and p.strip():
                    preds.append(p.strip())
            except Exception as e:
                print(f"    (run error: {e})")
            if a.dynamic and len(preds) >= 3:
                c = Counter(preds)
                top, cnt = c.most_common(1)[0]
                if cnt >= max(2, len(preds) // 2 + 1):
                    break
        pred = None
        if preds:
            if a.self_verify:
                pred = self_verify(q, preds)
            elif a.cluster:
                pred = cluster_vote(q, preds)
            elif a.weighted:
                pred = weighted_vote(preds)
            else:
                pred = Counter(preds).most_common(1)[0][0]
        ok, reason = judge(q, gt, pred or "")
        correct += ok
        print(f"[{i}] L{row.get('Level')} ok={ok}")
        print(f"  Q  : {q[:80]}")
        print(f"  GT : {gt[:70]} | PRED: {str(pred)[:70]}")
        print(f"  judge: {reason}")
        sys.stdout.flush()
    acc = correct / len(batch) if len(batch) else 0.0
    print(f"\nACC: {correct}/{len(batch)} = {acc:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
