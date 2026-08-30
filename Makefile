.PHONY: test install deps

# D0: host-agnostic core tests run with plain python3 + pytest (no deerflow).
test:
	python3 -m pytest tests -q

install:
	python3 -m pip install -e .[dev]

# Full stack (deerflow/langchain) — for later phases.
deps:
	python3 -m pip install -e '.[deerflow]'
