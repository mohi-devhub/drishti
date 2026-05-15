.PHONY: dev api worker web lint test audit

dev:
	@printf "Starting Drishti dev processes...\n"
	@trap 'kill 0' INT TERM EXIT; \
		uv run uvicorn drishti.app:create_app --factory --host $${DRISHTI_API_HOST:-0.0.0.0} --port $${DRISHTI_API_PORT:-8000} --reload & \
		uv run arq drishti.worker.WorkerSettings & \
		cd web && corepack pnpm dev

api:
	uv run uvicorn drishti.app:create_app --factory --host $${DRISHTI_API_HOST:-0.0.0.0} --port $${DRISHTI_API_PORT:-8000} --reload

worker:
	uv run arq drishti.worker.WorkerSettings

web:
	cd web && corepack pnpm dev

lint:
	uv run ruff check .
	uv run black --check .

test:
	uv run pytest

audit:
	uvx pip-audit
	cd web && corepack pnpm audit --audit-level moderate
