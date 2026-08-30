"""deerflow-harness-ext: model-agnostic harness strategy layer hosted on DeerFlow.

The `core` and `policies` subpackages are HOST-AGNOSTIC and must not import
DeerFlow/LangChain types (see engineering report contract). The `deerflow`
subpackage is the adapter layer that depends on deerflow+langchain.
"""

__version__ = "0.1.0"
