"""TheAgentCompany: serial in-container agent (no OpenHands, no concurrency).

Uses WSL distro `tac-docker` docker. Tasks with no service deps (install-go /
install-openjdk) run immediately. GitLab-backed tasks run only if api-server
healthchecks pass.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from apodex_harness import call_model

DECRYPTION = "theagentcompany is all you need"
IMAGE_TMPL = "ghcr.io/theagentcompany/{task}-image:1.0.0"
NEEDS_GITLAB = {"sde-update-readme", "sde-reply-community-issue-with-fixed-reply"}
DEFAULT_PATH = (
    "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:"
    "/usr/local/go/bin:/usr/lib/jvm/java-17-openjdk-amd64/bin"
)

SYSTEM = (
    "You are a software engineer inside a Debian container. Complete /instruction/task.md.\n"
    "Reply with ONE JSON object only: {\"cmd\": \"one bash command\"} or {\"done\": true}.\n"
    "Rules:\n"
    "- Non-interactive: DEBIAN_FRONTEND=noninteractive, apt-get -y.\n"
    "- After installing Go, run: ln -sf /usr/local/go/bin/go /usr/bin/go && go version\n"
    "  A login-shell PATH is NOT enough; the grader calls `go` with a clean PATH.\n"
    "- After installing OpenJDK 17, ensure `java --version` works (apt usually puts java in /usr/bin).\n"
    "- Do NOT send {\"done\": true} until the version command succeeds in the LAST output.\n"
    "- Do not read /utils/evaluator.py."
)

APT_BOOTSTRAP = r"""
set -e
export DEBIAN_FRONTEND=noninteractive
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
if [ -f /etc/apt/sources.list ]; then
  sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list || true
  sed -i 's|https://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list || true
fi
apt-get update -o Acquire::Retries=3 || true
"""


def _docker_cmd() -> Optional[List[str]]:
    import shutil
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


def _win_to_wsl(path: Path) -> str:
    p = str(path.resolve())
    if len(p) >= 2 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    return p.replace("\\", "/")


def _run(cmd: List[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


def gitlab_ready() -> bool:
    import shutil
    wsl = shutil.which("wsl")
    if not wsl:
        return False
    r = _run(
        [wsl, "-d", "tac-docker", "-u", "root", "--",
         "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         "http://127.0.0.1:2999/api/healthcheck/gitlab"],
        timeout=15,
    )
    return (r.stdout or "").strip() == "200"


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        o = json.loads(m.group(0))
        return o if isinstance(o, dict) else None
    except ValueError:
        return None


def _exec(dcmd: List[str], name: str, bash_cmd: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return _run(
        dcmd + ["exec",
                "-e", f"PATH={DEFAULT_PATH}",
                "-e", "DEBIAN_FRONTEND=noninteractive",
                name, "bash", "-lc", bash_cmd],
        timeout=timeout,
    )


def _not_actually_done(task: str, probe: str) -> Optional[str]:
    low = (probe or "").lower()
    if task == "sde-install-go":
        if "go version" in low and "1.17" in low:
            return None
        return "NOT DONE. Grader runs `go version` on a clean PATH. Install Go 1.17 and `ln -sf /usr/local/go/bin/go /usr/bin/go`, then run `go version`."
    if task == "sde-install-openjdk":
        if "openjdk" in low and "17" in low:
            return None
        return "NOT DONE. Grader runs `java --version`. Install OpenJDK 17 noninteractively, then run `java --version`."
    return None


def run_task(task: str, out_dir: str, max_steps: int = 25) -> Dict[str, Any]:
    dcmd = _docker_cmd()
    if not dcmd:
        return {"id": task, "ok": False, "skipped": True, "reason": "docker unavailable"}
    if task in NEEDS_GITLAB and not gitlab_ready():
        return {"id": task, "ok": False, "skipped": True, "reason": "api-server/gitlab not healthy"}

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    image = IMAGE_TMPL.format(task=task)
    name = f"apodex-tac-{task}"
    wsl_out = _win_to_wsl(out)

    _run(dcmd + ["rm", "-f", name], timeout=60)
    start = _run(
        dcmd + ["run", "-d", "--name", name, "--network", "host",
                "-v", f"{wsl_out}:/outputs",
                "-e", "SERVER_HOSTNAME=localhost",
                "-e", f"PATH={DEFAULT_PATH}",
                "-e", "DEBIAN_FRONTEND=noninteractive",
                image, "sleep", "7200"],
        timeout=120,
    )
    if start.returncode != 0:
        return {"id": task, "ok": False, "error": (start.stderr or start.stdout or "")[:800]}

    rec: Dict[str, Any] = {"id": task, "ok": False, "container": name}
    try:
        env_llm = [
            "-e", f"LITELLM_API_KEY={os.environ.get('APODEX_API_KEY') or ''}",
            "-e", f"LITELLM_BASE_URL={os.environ.get('APODEX_BASE_URL') or 'https://api.apodex.ai/v1'}",
            "-e", f"LITELLM_MODEL={os.environ.get('APODEX_MODEL') or 'apodex-1.1'}",
            "-e", "SERVER_HOSTNAME=localhost",
            "-e", f"PATH={DEFAULT_PATH}",
        ]
        print(f"  [tac {task}] init.sh", flush=True)
        init = _run(dcmd + ["exec"] + env_llm + [name, "bash", "/utils/init.sh"], timeout=600)
        (out / "init.log").write_text((init.stdout or "") + "\n" + (init.stderr or ""), encoding="utf-8")

        print(f"  [tac {task}] apt bootstrap", flush=True)
        boot = _exec(dcmd, name, APT_BOOTSTRAP, timeout=300)
        (out / "bootstrap.log").write_text((boot.stdout or "") + "\n" + (boot.stderr or ""), encoding="utf-8")

        cat = _exec(dcmd, name, "cat /instruction/task.md", timeout=30)
        instruction = cat.stdout or ""
        last = ""
        cmds: List[str] = []
        for i in range(max_steps):
            user = f"TASK:\n{instruction}\n\nLAST:\n{last[-4000:]}\n\nJSON only."
            reply = call_model(SYSTEM, [{"role": "user", "content": user}])
            obj = _extract_json(reply) or {}
            if obj.get("done"):
                probe = _exec(dcmd, name, "go version 2>&1; java --version 2>&1; echo PATH=$PATH", timeout=30)
                msg = _not_actually_done(task, (probe.stdout or "") + (probe.stderr or ""))
                if msg:
                    print(f"  [tac {task} {i+1}] premature done, continue", flush=True)
                    last = msg + "\n" + (probe.stdout or "")[-1500:]
                    continue
                print(f"  [tac {task} {i+1}] DONE", flush=True)
                break
            cmd = str(obj.get("cmd") or "").strip()
            if not cmd:
                last = "invalid JSON; send {\"cmd\": \"...\"} or {\"done\": true}"
                continue
            print(f"  [tac {task} {i+1}/{max_steps}] {cmd[:140]}", flush=True)
            cmds.append(cmd)
            ex = _exec(dcmd, name, cmd, timeout=900)
            last = f"exit={ex.returncode}\n{(ex.stdout or '')[-2000:]}\n{(ex.stderr or '')[-1000:]}"
            time.sleep(1)

        (out / "commands.json").write_text(json.dumps(cmds, indent=2), encoding="utf-8")
        (out / "trajectory.txt").write_text("\n\n".join(cmds), encoding="utf-8")

        print(f"  [tac {task}] eval.py", flush=True)
        ev = _run(
            dcmd + ["exec",
                    "-e", f"DECRYPTION_KEY={DECRYPTION}",
                    "-e", f"LITELLM_API_KEY={os.environ.get('APODEX_API_KEY') or ''}",
                    "-e", f"LITELLM_BASE_URL={os.environ.get('APODEX_BASE_URL') or 'https://api.apodex.ai/v1'}",
                    "-e", f"LITELLM_MODEL={os.environ.get('APODEX_MODEL') or 'apodex-1.1'}",
                    "-e", f"PATH={DEFAULT_PATH}",
                    name, "bash", "-lc",
                    f"export PATH={DEFAULT_PATH}; python_default /utils/eval.py --result_path /outputs/eval.json"],
            timeout=180,
        )
        (out / "eval.log").write_text((ev.stdout or "") + "\n" + (ev.stderr or ""), encoding="utf-8")
        eval_path = out / "eval.json"
        rec["eval"] = json.loads(eval_path.read_text(encoding="utf-8")) if eval_path.is_file() else None
        rec["ok"] = True
        rec["n_cmds"] = len(cmds)
        if rec.get("eval"):
            rec["score"] = (rec["eval"].get("final_score") or {}).get("result")
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    finally:
        _run(dcmd + ["rm", "-f", name], timeout=60)
    return rec
