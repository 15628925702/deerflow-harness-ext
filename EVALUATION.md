# Evaluation: policy harness + apodex model on executable-world

Run via `examples/apodex_harness.py` (host-agnostic policy layer + apodex model,
OpenAI-compatible) against the Apodex `executable-world-examples` kit.
Date 2026-08-29. Default model `apodex-1.1-mini` (free). Proxy: Singapore node
(apodex is geo-blocked for mainland-CN exit IPs; HK nodes are rejected, SG/JP/US work).

## Results (apodex-1.1-mini)

| task | score | notes |
|---|---|---|
| verify_solutions | **1.0** | candidate verification (list -> probe -> submit) |
| clinical_signal | **1.0** | gated field verification handled |
| corpus_dedup | **1.0** | dual-objective (dedup_f1 + leak_recall) thresholds |
| treatment_response | **1.0** | feature selection + timely submit |
| corpus_procurement | **0.0** | failed contamination gate (see below) |

**4 / 5 tasks at 1.0 with the free model.** The policy layer (failure / stall /
permissions / context / recovery) never hurt a task and stays a clean
host-agnostic core.

## Capability gaps found, and the harness fixes applied

1. **Model explores but does not submit** (treatment_response scored nothing;
   corpus_procurement once submitted an empty plan). Fix: a step- AND
   budget-aware `SUBMIT` reminder + a prompt rule "you MUST submit a concrete,
   executable result". → treatment_response went to **1.0**.
2. **Windows console / file encoding crash** on non-ASCII observations (`²`, GBK
   vs UTF-8). Fix: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`
   in the harness + run with `PYTHONUTF8=1` (the example-kit `engine.py` writes
   trajectory with the locale encoding). On a UTF-8 host this is a non-issue.
3. **corpus_procurement lands spam** → contamination > 15% hard gate → 0. The
   free model cannot reliably attribute multi-source honeypot/mirror/contamination
   and still land a clean procurement plan. A data-traps prompt line helps but is
   not enough at this model size. **This is a model-capability limit, not a
   harness defect.** A stronger model is expected to clear it.

## Harness takeaways for "official" use

- Submission reminders are valuable on budget-scarce tasks but must not fire too
  early on exploration-heavy tasks (make the trigger tunable, e.g. min-budget
  threshold or step fraction).
- The strategy layer is exercised end-to-end here on top of the 70+ unit tests:
  it is observable (every decision lands in the ledger), replaceable, and
  host-agnostic.
- Reproduce: `PYTHONPATH=<repo>/src:<repo>/examples APODEX_API_KEY=... APODEX_MODEL=... \
  python run_task.py --task <id> --agent apodex_harness:solve`
