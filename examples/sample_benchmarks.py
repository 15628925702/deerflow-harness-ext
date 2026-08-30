"""Stratified sampling of Apodex deep-research benchmarks.

Reads each benchmark's standardized_data.jsonl and writes a stratified sample
to <out>/<Name>/sampled.jsonl. Stratification key is chosen per benchmark from
its metadata (topic/subject/category); benchmarks with no useful stratum use
uniform sampling. Fixed seed => reproducible.

Usage: python sample_benchmarks.py --root <datasets_dir> --out <out_dir>
"""
from __future__ import annotations

import argparse
import json
import os
import random

ROOT_DEFAULT = None  # filled from --root

# benchmark -> (target sample size, strat field or None)
PLAN = {
    "BrowseComp":                  (150, "problem_topic"),
    "BrowseComp-ZH":               (50,  "topic"),
    "DeepSearchQA":                (150, "problem_topic"),
    "WideSearch":                  (80,  None),
    "FrontierScience-Research":    (50,  "subject"),
    "FrontierScience-Olympiad":    (50,  "subject"),
    "SUPERChem-Text":              (100, "category"),
    "XBench-DeepResearch-202510":  (60,  None),
}
SEED = 42


def strat_value(row, field):
    if not field:
        return None
    m = row.get("metadata")
    if isinstance(m, dict) and field in m:
        return m[field]
    return row.get(field) or "NA"


def sample_one(name, n, field, rows, rng):
    if len(rows) <= n:
        return rows
    if field is None:
        # uniform; only stratify if field produced >1 distinct value
        return rng.sample(rows, n)
    groups = {}
    for r in rows:
        groups.setdefault(strat_value(r, field), []).append(r)
    if len(groups) <= 1:
        return rng.sample(rows, n)
    # per-stratum proportional allocation, round up, then trim to n
    sel = []
    total = len(rows)
    for k, v in groups.items():
        want = max(1, round(n * len(v) / total))
        sel += rng.sample(v, min(want, len(v)))
    if len(sel) > n:
        sel = rng.sample(sel, n)
    elif len(sel) < n:
        # top up from rows not yet selected
        have = {id(r) for r in sel}
        rest = [r for r in rows if id(r) not in have]
        sel += rng.sample(rest, min(n - len(sel), len(rest)))
    return sel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="datasets dir (contains <Name>/standardized_data.jsonl)")
    ap.add_argument("--out", required=True, help="output dir for sampled files")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    total = 0
    for name, (n, field) in PLAN.items():
        src = os.path.join(a.root, name, "standardized_data.jsonl")
        if not os.path.exists(src):
            print(f"!! missing {src}")
            continue
        rows = [json.loads(l) for l in open(src, encoding="utf-8")]
        rng = random.Random(SEED + hash(name) % 100000)
        sampled = sample_one(name, n, field, rows, rng)
        out = os.path.join(a.out, f"{name}.jsonl")
        with open(out, "w", encoding="utf-8") as f:
            for r in sampled:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        total += len(sampled)
        print(f"{name:28s} {len(rows):5d} -> {len(sampled):4d}  (strat={field})")
    print(f"总采样题数: {total}  (x{3} self-consistency = {total*3} 次推理)")


if __name__ == "__main__":
    raise SystemExit(main())
