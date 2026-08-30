"""DeerFlow adapter layer. This subpackage MAY import deerflow/langchain.

The core + policies above must NOT import anything from here (host-agnostic
contract). Build middleware only when the heavy deps are installed.
"""
