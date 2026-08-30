.PHONY: test lint typecheck check demo demo-embedded demo-distributed demo-research build dev-up dev-down

test:
	PYTHONPATH=src python -m unittest discover -s tests -v

lint:
	ruff check src tests examples

typecheck:
	mypy src/noema

check: test lint typecheck
	PYTHONPATH=src python -m compileall -q src examples

demo:
	PYTHONPATH=src python examples/autonomous_incident_agent.py

demo-embedded:
	MODE=embedded PYTHONPATH=src python examples/autonomous_incident_agent.py

demo-distributed:
	MODE=distributed PYTHONPATH=src python examples/autonomous_incident_agent.py

demo-research:
	PYTHONPATH=src python examples/autonomous_research_loop.py

build:
	python -m build

dev-up:
	docker compose up -d --wait

dev-down:
	docker compose down
