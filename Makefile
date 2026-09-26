.PHONY: help bootstrap dev api worker scheduler web test jazz-inspect sync-jazz lint

help:
	@echo "Targets: bootstrap dev api worker scheduler web test jazz-inspect sync-jazz lint"

bootstrap:
	cd services/backend && uv sync && uv run python ../../scripts/bootstrap_appwrite.py

dev:
	@echo "Run: pnpm --dir apps/web dev  +  backend api/worker/scheduler in separate terminals"

api:
	cd services/backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

worker:
	cd services/backend && uv run python -m app.jobs.worker

scheduler:
	cd services/backend && uv run python -m app.jobs.scheduler

web:
	pnpm --dir apps/web dev

test:
	cd services/backend && uv run pytest -q

lint:
	cd services/backend && uv run ruff check app tests ../../scripts

jazz-inspect:
	cd services/backend && uv run python ../../scripts/jazz_inspect.py

sync-jazz:
	cd services/backend && uv run python ../../scripts/cli.py sync-jazz
