"""Coding subagent integration (D4-D6): native agent + sandbox/model bridges."""
from .agent import CodingAgent
from .config import DEFAULT_CODING_TOOLS, CodingConfig
from .model_bridge import ModelBridge
from .prompt import build_system_prompt
from .result import CodingResult
from .sandbox_environment import ActionRecord, SandboxEnvironment

__all__ = ["CodingAgent", "CodingConfig", "DEFAULT_CODING_TOOLS",
           "build_system_prompt", "CodingResult", "ModelBridge",
           "SandboxEnvironment", "ActionRecord"]
