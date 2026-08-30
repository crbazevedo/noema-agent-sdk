.PHONY: test lint typecheck check demo demo-research build

test:
	PYTHONPATH=src python -m unittest discover -s tests -v

lint:
	ruff check src tests examples

typecheck:
	mypy src/noema

check: test
	PYTHONPATH=src python -m compileall -q src examples

demo:
	PYTHONPATH=src python examples/autonomous_incident_agent.py

demo-research:
	PYTHONPATH=src python examples/autonomous_research_loop.py

build:
	python -m build
