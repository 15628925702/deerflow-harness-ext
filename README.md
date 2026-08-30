# deerflow-harness-ext

Model-agnostic harness strategy layer hosted on DeerFlow (see
`DeerFlow_Host_Model_Agnostic_Harness_Engineering_Report`).

## D0 — extension skeleton

- Host-agnostic core: `core/` (state, decisions, engine) — stdlib only.
- Policy suite: `policies/` (context, failure, permissions) — stdlib only.
- DeerFlow adapter (lazy-import): `deerflow/middleware.py`, `deerflow/config.py`.
- Dry-run ledger: `telemetry/`.

## D1 — guardrails

- `core/risk.py`: tool risk classifier (dangerous commands, protected paths, mutating tools).
- `policies/permissions.py`: permission modes (default/plan/approve) -> allow/deny/require_approval.

## D2 — Failure / Stall detection
- `core/failure.py`: stable failure fingerprinting (noise-stripped, key-order stable).
- `core/progress.py`: bounded no-progress tracking (accepts str/dict output).
- `policies/failure.py`, `policies/stall.py`: repeat-failure and stall hints.

## D3 — Recovery / Context
- `policies/recovery.py`: transient recovery-hint injection (max-N, cleared on new evidence).
- `policies/context.py`: compaction trigger + `preserve` fields for the summarizer.

## D4 — Native coding subagent
- `coding/`: mini-SWE-inspired linear coding loop, narrow tools, test-driven.

## D5 — Workspace checkpoint + review
- `checkpoint/`: git-based snapshot + store (code audit; distinct from conversation replay).
- `review/`: read-only completion review of a coding result.

## D6 — mini-SWE worker bridge
- `coding/sandbox_environment.py`, `coding/model_bridge.py`: bridge sandbox/model to mini-SWE shapes.

## D7 — Cross-host core
- `core/corpus.py`: detector corpus to verify cross-host decision consistency.
- `deerflow/state_adapter.py`: host-neutral state mapping (a Pi adapter is the same shape).

## End-to-end demo (apodex + executable-world)
`examples/apodex_harness.py` runs the policy layer as a harness middleware driving
an executable-world task with the apodex model (see its docstring for the run
command). Evaluated on all 5 example tasks — **4/5 at score 1.0 with the free
model**. See `EVALUATION.md` for per-task results, capability gaps and the fixes
applied.

## Evaluation results (apodex-1.1, best)

| Task / Benchmark | Best |
|---|---|
| executable-world verify_solutions | 1.0 |
| executable-world clinical_signal | 1.0 |
| executable-world corpus_dedup | 1.0 |
| executable-world treatment_response | 1.007 |
| executable-world corpus_procurement | 0.96 |
| GAIA validation (self-consistency majority) | 60% |

Recommended: self-consistency majority voting (`--self-consistency N`) is the most
effective model-agnostic boost on apodex-1.1. See `examples/run_gaia.py`.

## Verified in a real LangGraph agent

`tests/test_langchain_integration.py` builds `HarnessPolicyMiddleware` via
`langchain.agents.create_agent(..., middleware=[mw])` and asserts policy
decisions land in the ledger. Skipped when langchain is not installed.

Contract: `core`/`policies` never import `deerflow.*` or LangChain types;
the package depends only on `deerflow.*` for its adapter layer.

## Run

```bash
python3 -m pytest tests -q                       # host-agnostic (no deerflow)
make test
# with the deerflow stack installed:
PYTHONPATH=/root/autodl-tmp/harness-site:src python3 -m pytest tests -q
```
