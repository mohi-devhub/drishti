# Drishti - AI ops analyst for D2C brands

Drishti connects Shopify, Shiprocket, and Razorpay data into one merchant-scoped ops workspace with cited chat answers and a read-only agent run log.

## Current Status

Day 0 scaffold is in place:

- FastAPI backend with `/health`
- Arq worker entrypoint
- Next.js app under `web/`
- Shared env templates
- Local `make dev` command
- Railway service notes

The detailed product, architecture, schema, connector, citation, agent, and build plans live in `docs/`.

## Local Development

```bash
cp .env.example .env
cp web/.env.example web/.env.local
uv sync
cd web && corepack pnpm install
make dev
```

Backend health check:

```bash
curl http://localhost:8000/health
```

Frontend:

```bash
open http://localhost:3000
```

## External Setup Still Needed

- Supabase project and Postgres connection string
- Railway project with `api`, `worker`, `web`, and Redis services
- Clerk app with a JWT template that includes `merchant_id`
- Logfire project and write token
