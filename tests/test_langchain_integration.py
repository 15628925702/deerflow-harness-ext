"""Integration test: HarnessPolicyMiddleware inside a real LangGraph agent.

Requires langchain + langgraph (the `deerflow` extra). Skipped automatically
when they are not importable, so the host-agnostic default test run still works.
Run with: PYTHONPATH=/root/autodl-tmp/harness-site:src python3 -m pytest tests
"""
import pytest
pytest.importorskip("langchain")

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from deerflow_harness_ext.core.engine import HarnessEngine
from deerflow_harness_ext.core.state import HarnessState
from deerflow_harness_ext.policies.context import ContextPolicy
from deerflow_harness_ext.deerflow.middleware import build_middleware


@tool
def echo(x: str) -> str:
    """Echo the input back."""
    return x


class Store:
    def load(self, config):
        s = HarnessState()
        s.context_fraction = 0.95
        return s

    def persist(self, s):
        pass


def test_middleware_runs_in_real_langgraph_agent():
    calls = [0]

    class FakeModel(BaseChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                msg = AIMessage(content="", tool_calls=[
                    {"name": "echo", "args": {"x": "hi"}, "id": "1", "type": "tool_call"}])
            else:
                msg = AIMessage(content="done")
            return ChatResult(generations=[ChatGeneration(message=msg)])

        @property
        def _llm_type(self) -> str:
            return "fake"

    eng = HarnessEngine(policies=[ContextPolicy(target_fraction=0.85)])
    mw = build_middleware(eng, Store())
    agent = create_agent(FakeModel(), tools=[echo], middleware=[mw])
    agent.invoke({"messages": [HumanMessage(content="run")]})

    ds = eng.summary()
    assert any(d["policy"] == "context" and d["action"] == "compact" for d in ds)
    assert len(ds) >= 2  # at least before+after for the first model turn
