.PHONY: help deploy-local verify-local deploy-local-active verify-local-active deploy-production verify-production test lint

help:
	@echo "Targets: deploy-local verify-local deploy-local-active verify-local-active deploy-production verify-production test lint"

deploy-local:
	uv run --project services/backend python scripts/deploy_appwrite.py deploy --local --paused

verify-local:
	uv run --project services/backend python scripts/deploy_appwrite.py verify --local --paused

deploy-local-active:
	uv run --project services/backend python scripts/deploy_appwrite.py deploy --local

verify-local-active:
	uv run --project services/backend python scripts/deploy_appwrite.py verify --local

deploy-production:
	uv run --project services/backend python scripts/deploy_appwrite.py deploy

verify-production:
	uv run --project services/backend python scripts/deploy_appwrite.py verify

test:
	uv run --project services/backend pytest services/backend/tests -q
	pnpm --dir apps/web test

lint:
	uv run --project services/backend ruff check services/backend/app services/backend/tests infra/appwrite scripts --config services/backend/pyproject.toml
