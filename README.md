EVM Decoder – Scaffold

What’s included
- FastAPI app with basic health endpoints
- Celery app with named queues: ingest, decode, prices, analytics
- Redis-backed rate limiter (with in-process fallback)
- Etherscan V2 client skeleton (block-window paginator stub)
- PriceService skeleton (CoinGecko → DeFiLlama → Alchemy fallback with daily budget)
- Example SQL migration (DDL) with core tables
- Docker compose for Redis

Quick start
1) Copy env file
   cp .env.example .env

2) Start Redis (local)
   docker compose up -d redis

   Notes:
   - The container maps host port 6380 → container 6379.
   - Set REDIS_URL=redis://localhost:6380/0 (default in .env.example).
   - Or use Upstash/managed Redis and set REDIS_URL accordingly (e.g., rediss://...)

3) Run API
   uvicorn evm_decoder.api.main:app --reload

4) Run workers
   celery -A evm_decoder.celery_app.celery_app worker -Q ingest -l info
   celery -A evm_decoder.celery_app.celery_app worker -Q decode -l info
   celery -A evm_decoder.celery_app.celery_app worker -Q prices -l info
   celery -A evm_decoder.celery_app.celery_app worker -Q analytics -l info

Environment
- SUPABASE_URL is used for Supabase project context. If you have a direct Postgres URL (e.g., for workers), set DATABASE_URL or SUPABASE_DB_URL.
- Respecting free-tier limits: ETHERSCAN_RPS, COINGECKO_RPS, LLAMA_RPS control RPS (integers or decimals, e.g., 0.5 for 1 req/2s). PRICE_DAILY_BUDGET_ALCHEMY limits fallback spend (0 disables).
- CoinGecko auth: set `COINGECKO_API_TIER` to `demo` (default) and provide `COINGECKO_API_KEY` to send `x_cg_demo_api_key` to `https://api.coingecko.com/api/v3/`. Set `COINGECKO_API_TIER=pro` to use `https://pro-api.coingecko.com/api/v3/` with header `x-cg-pro-api-key`.

Database (Postgres/Supabase)
- Set `DATABASE_URL` (recommended) or `SUPABASE_DB_URL` for the workers/API. Example: `postgresql+psycopg://user:pass@host:5432/postgres?sslmode=require`.
- Apply migrations:
  - `psql "$DATABASE_URL" -f migrations/001_init.sql`
  - `psql "$DATABASE_URL" -f migrations/002_transactions.sql`
- Notes: Use port 5432 for long-lived workers; 6543 for serverless burst connections with prepared statements disabled.

Ingestion endpoints and tasks
- Trigger address ingest (queues a Celery task):
  - `POST /api/v1/ingest/address` with JSON `{ "chain_id": 1, "address": "0x...", "start_block": 0, "end_block": 99999999, "window": 10000 }`
- Workers to run:
  - `celery -A evm_decoder.celery_app.celery_app worker -Q ingest -l info`
- Current persistence:
  - Transactions → `transactions` table (upsert on (chain_id, hash))
  - Logs → `logs` table (linked to `transactions.id` via `tx_id`)

Supabase CLI workflow (optional but recommended)
- `supabase start` or `supabase db start` to run local stack.
- Place migrations under `supabase/migrations/` (already added for schema here).
- Apply locally: `supabase db reset` (drops and reapplies migrations).
- Point app to local DB: `DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres`.
- Link and push to remote: `supabase link --project-ref <ref>` then `supabase db push`.

Redis notes
- We use Redis for: Celery broker/results, rate limiting, and simple caches.
- If REDIS_URL is unset, the rate limiter falls back to an in-process limiter (fine for dev) but Celery requires a real Redis broker.

Status
This is a scaffold. Network client methods are wired with rate limiting and retries but contain TODOs to complete decoding logic, price provider request/response parsing, and persistence.
