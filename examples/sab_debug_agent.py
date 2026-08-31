"""ScienceAgentBench: generate one Python program per instance via apodex (no litellm).

Official docker eval needs OpenAI (visual judge) and is not used here.
This script writes pred programs, then optionally syntax-checks and tries a
short local execute against benchmark/ artifacts.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from apodex_harness import call_model


SYSTEM = (
    "You are an expert Python programming assistant for scientific data tasks. "
    "Write a complete, executable Python program. Wrap it in a ```python code block. "
    "Do not use !pip or interactive magics."
)


def _extract_python(text: str) -> str:
    m = re.search(r"```(?:python)?\s*([\s\S]*?)```", text or "", re.I)
    return (m.group(1) if m else (text or "")).strip()


def _load_sab():
    from datasets import load_dataset

    last = None
    for split in ("validation", "verified", "test", "train"):
        try:
            ds = load_dataset("osunlp/ScienceAgentBench", split=split)
            print(f"  [sab] loaded split={split} n={len(ds)}", flush=True)
            return ds
        except Exception as e:
            last = e
            continue
    raise RuntimeError(f"could not load osunlp/ScienceAgentBench ({last})")


def _deadline_up() -> bool:
    raw = os.environ.get("EVAL_DEADLINE_TS") or ""
    if not raw:
        return False
    try:
        return time.time() >= float(raw)
    except ValueError:
        return False


def run_instances(
    n: int,
    offset: int,
    out_dir: str,
    *,
    max_tokens: int = 4096,
    skip_existing: bool = True,
) -> dict:
    ds = _load_sab()
    os.makedirs(out_dir, exist_ok=True)
    log_path = Path(out_dir) / "sab_log.jsonl"
    pred_dir = Path(out_dir) / "pred_programs"
    pred_dir.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    end = min(len(ds), offset + n)
    for i in range(offset, end):
        if _deadline_up():
            print(f"  [sab] time budget hit before index {i}", flush=True)
            break
        ex = ds[i]
        inst = ex.get("task_inst") or ""
        tree = ex.get("dataset_folder_tree") or ""
        preview = ex.get("dataset_preview") or ""
        gold = ex.get("gold_program_name") or f"inst_{i}.py"
        pred = Path(out_dir) / f"pred_{gold}"
        pred_copy = pred_dir / gold
        if skip_existing and pred_copy.is_file() and pred_copy.stat().st_size > 20:
            code = pred_copy.read_text(encoding="utf-8", errors="replace")
            rec = {
                "index": i, "gold_program_name": gold, "pred": str(pred),
                "chars": len(code), "reused": True, "ok": True,
            }
            print(f"  [sab {i+1-offset}/{end-offset}] {gold} (reuse {len(code)} chars)", flush=True)
            rows.append(rec)
            continue
        user = (
            f"TASK:\n{inst}\n\nDATASET TREE:\n{tree}\n\nPREVIEW:\n{str(preview)[:2500]}\n"
            "Write the full program now."
        )
        print(f"  [sab {i+1-offset}/{end-offset}] {gold}", flush=True)
        t0 = time.time()
        rec: Dict[str, Any] = {"index": i, "gold_program_name": gold, "pred": str(pred), "ok": False}
        try:
            reply = call_model(SYSTEM, [{"role": "user", "content": user}], max_tokens=max_tokens)
            code = _extract_python(reply)
            pred.write_text(code, encoding="utf-8")
            pred_copy.write_text(code, encoding="utf-8")
            rec.update({"chars": len(code), "ok": bool(code.strip()), "elapsed_s": round(time.time() - t0, 1)})
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["elapsed_s"] = round(time.time() - t0, 1)
            print(f"    FAIL {rec['error']}", flush=True)
        rows.append(rec)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        pause = float(os.environ.get("DEBUG_SUITE_PAUSE") or 0)
        if pause and i + 1 < end:
            time.sleep(pause)
    return {
        "ok": True,
        "id": "sab-generate",
        "n": len(rows),
        "n_ok": sum(1 for r in rows if r.get("ok")),
        "log": str(log_path),
        "instances": rows,
    }


def score_instances(
    n: int,
    offset: int,
    out_dir: str,
    *,
    exec_timeout: int = 45,
    exec_budget_s: float = 2400.0,
) -> dict:
    """Syntax-check every pred; try a short execute from the SAB repo root.

    Programs read `benchmark/datasets/...` relative to cwd. Official docker
    scoring is not used (needs OpenAI visual judge + parallel workers).
    """
    import shutil

    ds = _load_sab()
    sab_root = Path(__file__).resolve().parents[2] / "benchmarks" / "scienceagentbench"
    pred_dir = Path(out_dir) / "pred_programs"
    rows: List[Dict[str, Any]] = []
    end = min(len(ds), offset + n)
    exec_left = float(exec_budget_s)
    score_log = Path(out_dir) / "sab_score.jsonl"
    scratch = Path(out_dir) / "exec_scratch.py"
    pred_results = sab_root / "pred_results"
    for i in range(offset, end):
        if _deadline_up():
            break
        ex = ds[i]
        gold = ex.get("gold_program_name") or f"inst_{i}.py"
        pred = pred_dir / gold
        rec: Dict[str, Any] = {"index": i, "gold_program_name": gold, "syntax_ok": False, "ran": False, "success": 0}
        if not pred.is_file():
            rec["error"] = "missing pred"
            rows.append(rec)
            continue
        code = pred.read_text(encoding="utf-8", errors="replace")
        rec["chars"] = len(code)
        try:
            ast.parse(code)
            rec["syntax_ok"] = True
        except SyntaxError as e:
            rec["error"] = f"SyntaxError: {e}"
            rows.append(rec)
            with open(score_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            continue
        if exec_left <= 5 or _deadline_up():
            rec["skip_exec"] = "budget"
            rows.append(rec)
            continue
        if pred_results.exists():
            shutil.rmtree(pred_results, ignore_errors=True)
        pred_results.mkdir(parents=True, exist_ok=True)
        scratch.write_text(code, encoding="utf-8")
        t0 = time.time()
        try:
            r = subprocess.run(
                [sys.executable, str(scratch)],
                cwd=str(sab_root), capture_output=True, text=True, timeout=exec_timeout,
                encoding="utf-8", errors="replace",
            )
            rec["ran"] = True
            rec["returncode"] = r.returncode
            rec["stderr_tail"] = (r.stderr or "")[-800:]
            out_fname = ex.get("output_fname") or ""
            produced = bool(out_fname) and (sab_root / out_fname).exists()
            rec["output_exists"] = produced
            rec["success"] = 1 if r.returncode == 0 and produced else 0
        except subprocess.TimeoutExpired:
            rec["ran"] = True
            rec["error"] = "Timeout"
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        rec["elapsed_s"] = round(time.time() - t0, 1)
        exec_left -= rec["elapsed_s"]
        print(
            f"  [sab-score {i+1-offset}/{end-offset}] {gold} syntax={rec['syntax_ok']} "
            f"success={rec.get('success')} {(rec.get('error') or rec.get('stderr_tail') or '')[:80]}",
            flush=True,
        )
        rows.append(rec)
        with open(score_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {
        "ok": True,
        "id": "sab-score",
        "n": len(rows),
        "syntax_ok": sum(1 for r in rows if r.get("syntax_ok")),
        "exec_success": sum(1 for r in rows if r.get("success")),
        "log": str(score_log),
        "instances": rows,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    gen = run_instances(a.n, a.offset, a.out)
    print(json.dumps({k: v for k, v in gen.items() if k != "instances"}, indent=2, ensure_ascii=False))
    if a.score:
        sc = score_instances(a.n, a.offset, a.out)
        print(json.dumps({k: v for k, v in sc.items() if k != "instances"}, indent=2, ensure_ascii=False))
