"""Bridge a chat model to a mini-SWE-style Model (D6)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List

ModelQuery = Callable[[List[Dict[str, str]]], str]


class ModelBridge:
    """Wraps a chat-model callable into the mini-SWE Model.query shape.

    `model_query` is a callable(messages) -> str (the host injects the real
    LLM, e.g. a DeerFlow BaseChatModel or the apodex endpoint). Every query is
    recorded on a trajectory for budget/telemetry.
    """

    def __init__(self, model_query: ModelQuery) -> None:
        self._query = model_query
        self.trajectory: List[Dict[str, Any]] = []

    def query(self, system: str, transcript: List[Dict[str, str]]) -> str:
        messages = [{"role": "system", "content": system}] + list(transcript)
        reply = self._query(messages)
        self.trajectory.append({
            "system": system,
            "transcript": list(transcript),
            "reply": reply,
        })
        return reply

    @property
    def call_count(self) -> int:
        return len(self.trajectory)
