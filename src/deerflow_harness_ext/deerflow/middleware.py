"""HarnessPolicyMiddleware: wraps every DeerFlow LLM turn with our engine.

Heavy deps (langchain/deerflow) are imported lazily so the host-agnostic core
stays importable without them. The middleware reads/writes HarnessState via a
`store` adapter (DeerFlow ThreadState), routes policy decisions to the engine,
and forwards every decision to an optional DryRunLedger for telemetry.
"""
from __future__ import annotations

from typing import Any, Optional

from ..core.engine import HarnessEngine
from ..core.state import HarnessState


def build_middleware(engine: HarnessEngine, store: Optional[Any] = None,
                     ledger: Optional[Any] = None) -> Any:
    """Construct a DeerFlow AgentMiddleware wired to `engine`.

    `store` is an adapter exposing load(runtime) -> HarnessState and
    persist(state). `ledger` (e.g. a DryRunLedger) receives every decision.
    """
    from langchain.agents.middleware import AgentMiddleware  # heavy dep, lazy

    class HarnessPolicyMiddleware(AgentMiddleware):
        def __init__(self, engine_: HarnessEngine, store_: Optional[Any] = None,
                     ledger_: Optional[Any] = None) -> None:
            self.engine = engine_
            self.store = store_
            self.ledger = ledger_
            super().__init__()

        def _load(self, runtime: Any) -> HarnessState:
            if self.store is not None:
                return self.store.load(runtime) or HarnessState()
            return HarnessState()

        def before_model(self, state: Any, runtime: Any):
            hstate = self._load(runtime)
            hstate.reset_transient()
            decisions = self.engine.before_model(hstate, {"thread_state": state})
            self._emit(decisions)
            return None

        def after_model(self, state: Any, runtime: Any):
            hstate = self._load(runtime)
            decisions = self.engine.after_model(hstate, {"thread_state": state})
            self._emit(decisions)
            if self.store is not None:
                self.store.persist(hstate)
            return None

        def _emit(self, decisions) -> None:
            if self.ledger is not None and decisions:
                self.ledger.extend(decisions)

    return HarnessPolicyMiddleware(engine, store, ledger)
