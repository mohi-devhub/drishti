api: uv run uvicorn drishti.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}
worker: uv run arq drishti.worker.WorkerSettings
web: cd web && corepack pnpm start
