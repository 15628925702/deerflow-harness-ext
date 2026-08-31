"""TRACES 调试集：单 key、严格顺序、禁止并发。

    python harness/examples/run_debug_suite.py
    python harness/examples/run_debug_suite.py --only ew
    python harness/examples/run_debug_suite.py --only dw,sab --dry-run

读 keys/apodex_keys.env，只用第一把 key，立刻丢掉 APODEX_KEYS，避免轮换打满账号限流。
结果落在 results/debug-suite/<timestamp>/ 。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
HARNESS_SRC = ROOT / "harness" / "src"
HARNESS_EX = ROOT / "harness" / "examples"
EW_DIR = ROOT / "benchmarks" / "executable-world" / "ew" / "executable-world-examples-main"
DW_DIR = ROOT / "benchmarks" / "discoveryworld"
SAB_DIR = ROOT / "benchmarks" / "scienceagentbench"
TAC_DIR = ROOT / "theagentcompany"
KEYS_FILE = ROOT / "keys" / "apodex_keys.env"
SUITE_YAML = ROOT / "eval" / "debug_suite.yaml"

_LIVE: Dict[str, Any] = {"path": None, "data": None, "t0": 0.0}

DEFAULT_SUITE: Dict[str, Any] = {
    "name": "traces-debug-suite",
    "concurrency": 1,
    "pause_seconds_between_tasks": 3,
    "stages": [
        {
            "id": "ew",
            "title": "executable-world",
            "skip_if_missing": False,
            "tasks": [
                {"id": "verify_solutions"},
                {"id": "clinical_signal"},
                {"id": "corpus_dedup"},
                {"id": "treatment_response"},
                {"id": "corpus_procurement"},
            ],
        },
        {
            "id": "dw",
            "title": "DiscoveryWorld",
            "skip_if_missing": True,
            "max_steps": 50,
            "tasks": [
                {"scenario": "Proteomics", "difficulty": "Easy", "seed": 0},
                {"scenario": "Space Sick", "difficulty": "Easy", "seed": 0},
                {"scenario": "Plant Nutrients", "difficulty": "Easy", "seed": 0},
            ],
        },
        {
            "id": "sab",
            "title": "ScienceAgentBench",
            "skip_if_missing": True,
            "instance_count": 3,
            "instance_offset": 0,
        },
        {
            "id": "tac",
            "title": "TheAgentCompany",
            "skip_if_missing": True,
            "tasks": [
                "sde-update-readme",
                "sde-install-go",
                "sde-install-openjdk",
                "sde-reply-community-issue-with-fixed-reply",
            ],
        },
    ],
}

TAC_IMAGE_TMPL = "ghcr.io/theagentcompany/{task}-image:1.0.0"


def _log(msg: str) -> None:
    print(msg, flush=True)


def load_env_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"missing env file: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")


def pin_single_key() -> int:
    """Keep only the first key. Unset APODEX_KEYS so nothing can rotate."""
    listed = [k.strip() for k in (os.environ.get("APODEX_KEYS") or "").split(",") if k.strip()]
    single = os.environ.get("APODEX_API_KEY") or ""
    if listed:
        os.environ["APODEX_API_KEY"] = listed[0]
        n = len(listed)
    elif single:
        n = 1
    else:
        raise SystemExit("need APODEX_API_KEY or APODEX_KEYS in keys/apodex_keys.env")
    os.environ.pop("APODEX_KEYS", None)
    os.environ["PYTHONUTF8"] = "1"
    os.environ.setdefault("APODEX_MODEL", "apodex-1.1")
    os.environ.setdefault("APODEX_BASE_URL", "https://api.apodex.ai/v1")
    return n


def _deadline_up() -> bool:
    raw = os.environ.get("EVAL_DEADLINE_TS") or ""
    if not raw:
        return False
    try:
        return time.time() >= float(raw)
    except ValueError:
        return False


def _remaining_s() -> Optional[float]:
    raw = os.environ.get("EVAL_DEADLINE_TS") or ""
    if not raw:
        return None
    try:
        return float(raw) - time.time()
    except ValueError:
        return None


def _heartbeat(msg: str) -> None:
    hb = os.environ.get("EVAL_HEARTBEAT")
    if hb:
        rem = _remaining_s()
        rem_s = f" remaining={int(rem)}s" if rem is not None else ""
        Path(hb).write_text(
            f"{datetime.now().isoformat(timespec='seconds')}{rem_s}  {msg}\n",
            encoding="utf-8",
        )
    _log(msg)


def _checkpoint() -> None:
    path = _LIVE.get("path")
    data = _LIVE.get("data")
    if not path or data is None:
        return
    data["elapsed_s"] = round(time.time() - float(_LIVE.get("t0") or time.time()), 1)
    rem = _remaining_s()
    if rem is not None:
        data["deadline_remaining_s"] = round(max(0.0, rem), 1)
    _write_json(Path(path), data)


def load_suite(path: Optional[Path] = None) -> Dict[str, Any]:
    yaml_path = path or SUITE_YAML
    if yaml_path.is_file():
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("stages"):
                return data
        except Exception as e:
            _log(f"[warn] could not parse {yaml_path} ({e}); using built-in suite")
    return DEFAULT_SUITE


def _prep_sys_path() -> None:
    for p in (str(HARNESS_SRC), str(HARNESS_EX), str(EW_DIR), str(DW_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _pause(seconds: float) -> None:
    if seconds and seconds > 0:
        time.sleep(float(seconds))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def run_ew(stage: Dict[str, Any], out: Path, pause: float, dry: bool) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not (EW_DIR / "run_task.py").is_file():
        return [{"id": "ew", "ok": False, "skipped": True, "reason": f"missing {EW_DIR}"}]
    tasks = [t["id"] if isinstance(t, dict) else t for t in (stage.get("tasks") or [])]
    if dry:
        return [{"id": tid, "dry_run": True} for tid in tasks]

    _prep_sys_path()
    from apodex_harness import solve  # noqa: WPS433
    from ew_examples import Episode, load_task  # noqa: WPS433

    prev = os.getcwd()
    try:
        os.chdir(EW_DIR)
        for i, tid in enumerate(tasks):
            if _deadline_up():
                rows.append({"id": tid, "ok": False, "skipped": True, "reason": "time_budget"})
                continue
            tdir = out / tid
            tdir.mkdir(parents=True, exist_ok=True)
            _log(f"\n=== EW {i+1}/{len(tasks)}  {tid} ===")
            rec: Dict[str, Any] = {"id": tid, "ok": False}
            t0 = time.time()
            try:
                task = load_task(tid, seed=0)
                ep = Episode(task, trajectory_path=str(tdir / "trajectory.jsonl"))
                solve(task, ep)
                result = ep.result or {
                    "score": None,
                    "note": "the episode never submitted, so it was not scored",
                }
                _write_json(tdir / "result.json", result)
                rec.update({
                    "ok": True,
                    "score": result.get("score"),
                    "feedback": result.get("feedback"),
                    "elapsed_s": round(time.time() - t0, 1),
                })
                _log(f"    score={rec['score']}  {rec['elapsed_s']}s")
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"
                rec["traceback"] = traceback.format_exc()
                _log(f"    FAIL {rec['error']}")
                (tdir / "error.txt").write_text(rec["traceback"], encoding="utf-8")
            rows.append(rec)
            _write_json(tdir / "summary.json", rec)
            _heartbeat(f"EW {tid} score={rec.get('score')} elapsed={rec.get('elapsed_s')}s")
            _checkpoint()
            if i < len(tasks) - 1:
                _pause(pause)
    finally:
        os.chdir(prev)
    return rows


def _safe_slug(text: str) -> str:
    """Windows-safe folder name (no : < > \" / \\ | ? *)."""
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad else c for c in text)
    return out.strip(" .") or "task"


def run_dw(stage: Dict[str, Any], out: Path, pause: float, dry: bool) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    tasks = stage.get("tasks") or []
    max_steps = int(stage.get("max_steps") or 20)
    if dry:
        return [{"id": f"{t.get('scenario')}/{t.get('difficulty')}", "dry_run": True} for t in tasks]

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    _prep_sys_path()
    try:
        from dw_debug_agent import _patch_pygame_win32_fonts, run_scenario  # noqa: WPS433
        _patch_pygame_win32_fonts()
        import pygame  # noqa: F401
        from discoveryworld.DiscoveryWorldAPI import DiscoveryWorldAPI  # noqa: F401
    except Exception as e:
        reason = f"DiscoveryWorld not importable ({type(e).__name__}: {e}). pip install -r benchmarks/discoveryworld/requirements.txt && pip install -e benchmarks/discoveryworld"
        _log(f"[skip dw] {reason}")
        return [{"id": "dw", "ok": False, "skipped": True, "reason": reason}]

    for i, t in enumerate(tasks):
        rem = _remaining_s()
        if _deadline_up() or (rem is not None and rem < 90):
            rows.append({
                "id": f"{t.get('scenario')}/{t.get('difficulty')}",
                "ok": False, "skipped": True, "reason": "time_budget",
            })
            continue
        scenario = t["scenario"]
        difficulty = t.get("difficulty") or "Easy"
        seed = int(t.get("seed") or 0)
        slug = _safe_slug(f"{scenario.replace(' ', '_')}_{difficulty}_s{seed}")
        tdir = out / slug
        prev = tdir / "summary.json"
        if (tdir / "scorecard.json").is_file() and prev.is_file():
            try:
                rec = json.loads(prev.read_text(encoding="utf-8"))
            except Exception:
                rec = {"id": slug, "ok": True, "reused": True}
            rec["reused"] = True
            rec["id"] = slug
            rows.append(rec)
            _log(f"\n=== DW {i+1}/{len(tasks)}  {scenario} {difficulty} seed={seed} (reuse) ===")
            continue
        try:
            tdir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            rec = {
                "id": slug, "scenario": scenario, "difficulty": difficulty, "seed": seed,
                "ok": False, "error": f"mkdir: {e}",
            }
            _log(f"    FAIL mkdir {slug}: {e}")
            rows.append(rec)
            continue
        _log(f"\n=== DW {i+1}/{len(tasks)}  {scenario} {difficulty} seed={seed} ===")
        rec: Dict[str, Any] = {"id": slug, "scenario": scenario, "difficulty": difficulty, "seed": seed, "ok": False}
        t0 = time.time()
        try:
            r = run_scenario(scenario, difficulty, seed, max_steps, str(tdir))
            rec.update(r)
            rec["elapsed_s"] = round(time.time() - t0, 1)
            rec.pop("scorecard", None)
            card = r.get("scorecard")
            rec["score_summary"] = _dw_score_summary(card)
            _log(f"    ok={rec.get('ok')}  {rec.get('score_summary')}  {rec['elapsed_s']}s")
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["traceback"] = traceback.format_exc()
            rec["elapsed_s"] = round(time.time() - t0, 1)
            _log(f"    FAIL {rec['error']}")
            (tdir / "error.txt").write_text(rec["traceback"], encoding="utf-8")
        rows.append(rec)
        _write_json(tdir / "summary.json", rec)
        _heartbeat(f"DW {slug} {rec.get('score_summary')} elapsed={rec.get('elapsed_s')}s")
        _checkpoint()
        if i < len(tasks) - 1:
            _pause(pause)
    return rows


def _dw_score_summary(card: Any) -> Any:
    if not card:
        return None
    if isinstance(card, list) and card:
        first = card[0] if isinstance(card[0], dict) else {}
        return {
            "completed": first.get("completed"),
            "score": first.get("score"),
            "scoreNormalized": first.get("scoreNormalized") or first.get("completedNormalizedScore"),
        }
    if isinstance(card, dict):
        return {k: card.get(k) for k in ("completed", "score", "scoreNormalized", "completedNormalizedScore") if k in card}
    return type(card).__name__


def run_sab(stage: Dict[str, Any], out: Path, pause: float, dry: bool) -> List[Dict[str, Any]]:
    n = int(stage.get("instance_count") or 3)
    offset = int(stage.get("instance_offset") or 0)
    do_score = bool(stage.get("score", True))
    if dry:
        return [{"id": f"sab[{offset}:{offset+n}]", "dry_run": True}]
    _prep_sys_path()
    try:
        from sab_debug_agent import run_instances, score_instances  # noqa: WPS433
    except Exception as e:
        reason = f"sab_debug_agent import failed: {e}"
        _log(f"[skip sab] {reason}")
        return [{"id": "sab", "ok": False, "skipped": True, "reason": reason}]
    rows: List[Dict[str, Any]] = []
    try:
        _log(f"\n=== SAB generate {n} instances from offset {offset} ===")
        t0 = time.time()
        r = run_instances(n, offset, str(out), max_tokens=int(stage.get("max_tokens") or 4096))
        r["elapsed_s"] = round(time.time() - t0, 1)
        slim = {k: v for k, v in r.items() if k != "instances"}
        _write_json(out / "generate_summary.json", slim)
        _heartbeat(f"SAB generated n={r.get('n')} ok={r.get('n_ok')} {r['elapsed_s']}s")
        rows.append(slim)
    except Exception as e:
        rec = {
            "id": "sab",
            "ok": False,
            "skipped": True,
            "reason": f"{type(e).__name__}: {e}",
            "hint": "pip install datasets; artifacts live under benchmarks/scienceagentbench/benchmark",
        }
        _log(f"[skip sab] {rec['reason']}")
        _write_json(out / "summary.json", rec)
        return [rec]
    if do_score and not _deadline_up():
        _log("\n=== SAB local score (syntax + short exec; not official docker) ===")
        t1 = time.time()
        sc = score_instances(
            n, offset, str(out),
            exec_timeout=int(stage.get("exec_timeout") or 45),
            exec_budget_s=float(stage.get("exec_budget_s") or 2400),
        )
        sc["elapsed_s"] = round(time.time() - t1, 1)
        slim_sc = {k: v for k, v in sc.items() if k != "instances"}
        _write_json(out / "score_summary.json", slim_sc)
        _heartbeat(
            f"SAB score syntax={slim_sc.get('syntax_ok')}/{slim_sc.get('n')} "
            f"exec_ok={slim_sc.get('exec_success')} {sc['elapsed_s']}s"
        )
        rows.append(slim_sc)
    _write_json(out / "summary.json", {"id": "sab", "parts": rows})
    return rows


def _docker_cmd() -> Optional[List[str]]:
    """Windows PATH docker, else WSL distro tac-docker (where images actually live)."""
    exe = shutil.which("docker")
    if exe:
        return [exe]
    wsl = shutil.which("wsl")
    if not wsl:
        return None
    r = subprocess.run(
        [wsl, "-d", "tac-docker", "-u", "root", "--", "docker", "info"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        return [wsl, "-d", "tac-docker", "-u", "root", "--", "docker"]
    return None


def _which_docker() -> Optional[str]:
    cmd = _docker_cmd()
    return " ".join(cmd) if cmd else None


def _image_present(image: str) -> bool:
    cmd = _docker_cmd()
    if not cmd:
        return False
    r = subprocess.run(
        cmd + ["images", "-q", image],
        capture_output=True, text=True, timeout=30,
    )
    return bool((r.stdout or "").strip())


def run_tac(stage: Dict[str, Any], out: Path, pause: float, dry: bool) -> List[Dict[str, Any]]:
    tasks = list(stage.get("tasks") or [])
    if dry:
        return [{"id": t, "dry_run": True} for t in tasks]

    docker = _docker_cmd()
    if not docker:
        rec = {
            "id": "tac",
            "ok": False,
            "skipped": True,
            "reason": "docker not available (Windows PATH or WSL distro tac-docker).",
        }
        _log(f"[skip tac] {rec['reason']}")
        _write_json(out / "summary.json", rec)
        return [rec]

    _prep_sys_path()
    from tac_debug_agent import run_task  # noqa: WPS433

    rows: List[Dict[str, Any]] = []
    for i, t in enumerate(tasks):
        if _deadline_up():
            rows.append({"id": t, "ok": False, "skipped": True, "reason": "time_budget"})
            continue
        image = TAC_IMAGE_TMPL.format(task=t)
        if not _image_present(image):
            rec = {"id": t, "ok": False, "skipped": True, "reason": f"image missing: {image}"}
            _log(f"    TAC {t}: SKIP {rec['reason']}")
            rows.append(rec)
            continue
        tdir = out / t
        tdir.mkdir(parents=True, exist_ok=True)
        _log(f"\n=== TAC {i+1}/{len(tasks)}  {t} ===")
        t0 = time.time()
        try:
            rec = run_task(t, str(tdir))
        except Exception as e:
            rec = {"id": t, "ok": False, "error": f"{type(e).__name__}: {e}"}
        rec["elapsed_s"] = round(time.time() - t0, 1)
        rows.append(rec)
        _write_json(tdir / "summary.json", rec)
        _heartbeat(f"TAC {t}: ok={rec.get('ok')} score={rec.get('score')} skipped={rec.get('skipped')}")
        _log(f"    TAC {t}: ok={rec.get('ok')} score={rec.get('score')} skipped={rec.get('skipped')} {rec.get('reason') or rec.get('error') or ''}")
        _checkpoint()
        if i < len(tasks) - 1:
            _pause(pause)
    _write_json(out / "summary.json", {"id": "tac", "tasks": rows})
    return rows


RUNNERS = {"ew": run_ew, "dw": run_dw, "sab": run_sab, "tac": run_tac}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Serial single-key TRACES debug suite")
    ap.add_argument("--only", default="", help="comma stages: ew,dw,sab,tac")
    ap.add_argument("--skip", default="", help="comma stages to skip")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pause", type=float, default=None, help="seconds between tasks (override yaml)")
    ap.add_argument("--out", default="", help="results directory (default results/debug-suite/<ts>)")
    ap.add_argument("--suite", default="", help="yaml path (default eval/debug_suite.yaml)")
    ap.add_argument("--max-hours", type=float, default=None, help="stop starting new tasks after this many hours")
    ap.add_argument("--workers", type=int, default=1, help="must stay 1; rejected otherwise")
    args = ap.parse_args()

    if args.workers != 1:
        raise SystemExit("concurrency is forbidden on this suite; --workers must be 1")

    os.environ["PYTHONUTF8"] = "1"
    load_env_file(KEYS_FILE)
    n_keys = pin_single_key()
    suite_path = Path(args.suite) if args.suite else SUITE_YAML
    if args.suite and not suite_path.is_absolute():
        suite_path = ROOT / args.suite
    suite = load_suite(suite_path)
    pause = args.pause if args.pause is not None else float(suite.get("pause_seconds_between_tasks") or 3)
    os.environ["DEBUG_SUITE_PAUSE"] = str(pause)
    max_hours = args.max_hours if args.max_hours is not None else suite.get("max_hours")
    if max_hours:
        os.environ["EVAL_DEADLINE_TS"] = str(time.time() + float(max_hours) * 3600.0)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_root = "long-eval" if max_hours else "debug-suite"
    out = Path(args.out) if args.out else ROOT / "results" / default_root / ts
    out.mkdir(parents=True, exist_ok=True)
    os.environ["EVAL_HEARTBEAT"] = str(out / "heartbeat.txt")

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    skip = {x.strip() for x in args.skip.split(",") if x.strip()}

    _log("=" * 64)
    _log("TRACES eval  |  single key  |  sequential  |  no concurrency")
    _log(f"suite     : {suite.get('name')}  ({suite_path})")
    _log(f"model     : {os.environ.get('APODEX_MODEL')}")
    _log(f"proxy     : {os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or '(none)'}")
    _log(f"keys file : {n_keys} listed → using 1, APODEX_KEYS unset")
    _log(f"pause     : {pause}s between tasks")
    _log(f"max_hours : {max_hours or '(none)'}")
    _log(f"out       : {out}")
    _log("=" * 64)

    all_rows: Dict[str, Any] = {
        "suite": suite.get("name"),
        "started": ts,
        "model": os.environ.get("APODEX_MODEL"),
        "concurrency": 1,
        "key_policy": "first_only",
        "dry_run": args.dry_run,
        "max_hours": max_hours,
        "stages": {},
    }
    prev_summary = out / "summary.json"
    if prev_summary.is_file() and not args.dry_run:
        try:
            prev = json.loads(prev_summary.read_text(encoding="utf-8"))
            if isinstance(prev, dict) and isinstance(prev.get("stages"), dict):
                all_rows["stages"] = prev["stages"]
                all_rows["original_started"] = prev.get("started")
                all_rows["resumed"] = ts
                _log(f"resuming previous summary with stages: {list(all_rows['stages'])}")
        except Exception as e:
            _log(f"[warn] could not merge previous summary: {e}")
    _LIVE["path"] = str(out / "summary.json")
    _LIVE["data"] = all_rows
    _LIVE["t0"] = time.time()
    _checkpoint()

    t_all = time.time()
    for stage in suite.get("stages") or []:
        sid = stage["id"]
        if only and sid not in only:
            continue
        if sid in skip:
            _log(f"\n--- skip {sid} (--skip) ---")
            continue
        if _deadline_up():
            _log(f"\n--- skip {sid} (time_budget) ---")
            all_rows["stages"][sid] = [{"id": sid, "ok": False, "skipped": True, "reason": "time_budget"}]
            continue
        _log(f"\n######## stage {sid}: {stage.get('title') or sid} ########")
        runner = RUNNERS.get(sid)
        if not runner:
            all_rows["stages"][sid] = [{"ok": False, "error": f"unknown stage {sid}"}]
            continue
        stage_out = out / sid
        stage_out.mkdir(parents=True, exist_ok=True)
        try:
            rows = runner(stage, stage_out, pause, args.dry_run)
        except Exception as e:
            _log(f"stage {sid} crashed: {type(e).__name__}: {e}")
            rows = list(all_rows.get("stages", {}).get(sid) or [])
            rows.append({"id": sid, "ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()})
        all_rows["stages"][sid] = rows
        _checkpoint()
        if not args.dry_run:
            _pause(pause)

    all_rows["elapsed_s"] = round(time.time() - t_all, 1)
    all_rows["finished"] = datetime.now().strftime("%Y%m%d-%H%M%S")
    _write_json(out / "summary.json", all_rows)
    _print_table(all_rows)
    _heartbeat(f"DONE elapsed={all_rows['elapsed_s']}s summary={out / 'summary.json'}")
    _log(f"\nsummary: {out / 'summary.json'}")
    return 0


def _print_table(all_rows: Dict[str, Any]) -> None:
    _log("\n" + "-" * 64)
    _log(f"{'stage':<8} {'task':<42} {'result'}")
    for sid, rows in (all_rows.get("stages") or {}).items():
        for rec in rows or []:
            tid = rec.get("id") or rec.get("gold_program_name") or sid
            if rec.get("dry_run"):
                res = "dry-run"
            elif rec.get("skipped"):
                res = "SKIP"
            elif rec.get("ok") is False:
                res = "FAIL"
            elif rec.get("score") is not None:
                res = f"score={rec.get('score')}"
            elif rec.get("score_summary"):
                res = str(rec.get("score_summary"))
            elif rec.get("n") is not None:
                res = f"n={rec.get('n')}"
            else:
                res = "ok" if rec.get("ok") else str(rec.get("reason") or "")
            _log(f"{sid:<8} {str(tid)[:42]:<42} {res}")
    _log("-" * 64)


if __name__ == "__main__":
    raise SystemExit(main())
