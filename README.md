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
  - By date (recommended): `POST /api/v1/ingest/address_by_date` with `{ "chain_id": 1, "address": "0x...", "start": "2024-01-01", "end": "2024-01-31" }`
    - The system maps dates → blocks and adaptively splits block ranges to avoid provider caps.
  - Block-range endpoint remains available for power users: `POST /api/v1/ingest/address`.
- Check task status:
  - `GET /api/v1/tasks/{task_id}` → `{ state: PENDING|STARTED|SUCCESS|FAILURE, result?: any }`
- Workers to run:
  - `celery -A evm_decoder.celery_app.celery_app worker -Q ingest -l info`
- Current persistence:
  - Transactions → `transactions` table (upsert on (chain_id, hash))
  - Receipts → update `status`, `gas_used`, `effective_gas_price`
  - Logs → `logs` table (per-receipt logs, linked via `tx_id`)
  - Token transfers → `token_transfers` (ERC-20/721 from logs)
  - Internal txs → `internal_transactions` via Etherscan `txlistinternal`
  - Traces (optional) → `traces` via Alchemy `trace_transaction` (budgeted)

Validation endpoints
- Address summary: `GET /api/v1/address/{chain_id}/{address}/summary?from_block=&to_block=`
- Address transactions: `GET /api/v1/address/{chain_id}/{address}/transactions?limit=25&offset=0&from_block=&to_block=`
- Address logs: `GET /api/v1/address/{chain_id}/{address}/logs?limit=25&offset=0&from_block=&to_block=`
- Address token transfers: `GET /api/v1/address/{chain_id}/{address}/token_transfers?limit=25&offset=0&from_block=&to_block=`
- Request traces for a tx: `POST /api/v1/traces/{chain_id}/{tx_hash}` and poll `/api/v1/tasks/{task_id}`

Smoke test script
- Run: `python scripts/smoke_api.py 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 --chain-id 1 --from-block 18000000 --to-block 18001000 --ingest`
- Options: `--base-url`, `--limit/--offset`, `--price-ts`.

CLI (optional)
- Base URL: set `API_BASE_URL` (defaults to `http://127.0.0.1:8000`).
- Usage: `python -m evm_decoder.cli --help`
- Examples:
  - Ingest by date (and wait):
    - `python3 -m evm_decoder.cli ingest-by-date --chain-id 1 --address 0xbce83d5060a7d7007fd7ca17301c1e5131b2d50e --start-date 2025-08-01 --end-date 2025-08-31 --wait`
  - Summary:
    - `python -m evm_decoder.cli summary --chain-id 1 --address 0xbce83d5060a7d7007fd7ca17301c1e5131b2d50e`
  - Transfers:
    - `python -m evm_decoder.cli transfers --chain-id 1 --address 0xbce83d5060a7d7007fd7ca17301c1e5131b2d50e --limit 10`
  - Traces:
    - `python3 -m evm_decoder.cli traces --chain-id 1 --tx-hash 0x... --wait`
  - Interactive menu (press / for menu):
    - `python3 -m evm_decoder.cli shell`
    - Defaults (override via env): `DEFAULT_WALLET`, `DEFAULT_CHAIN_ID`, `DEFAULT_WINDOW`
  - One-shot pipeline (ingest by date, optional traces):
    - `python3 -m evm_decoder.cli pipeline --chain-id 1 --address 0xbce83d5060a7d7007fd7ca17301c1e5131b2d50e --start-date 2025-08-01 --end-date 2025-08-31 --traces --max-traces 5`

Supabase CLI workflow (optional but recommended)
- `supabase start` or `supabase db start` to run local stack.
- Place migrations under `supabase/migrations/` (already added for schema here).
- Apply locally: `supabase db reset` (drops and reapplies migrations).
- Point app to local DB: `DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres`.
- Link and push to remote: `supabase link --project-ref <ref>` then `supabase db push`.

Traces (Alchemy, optional)
- Client and decode task added.
- Enable with `ALCHEMY_API_KEY` and a daily budget: `TRACES_DAILY_BUDGET_ALCHEMY` (>0).
- Per-chain hosts supported: ETH, Arbitrum, Optimism, Base, Polygon.

Redis notes
- We use Redis for: Celery broker/results, rate limiting, and simple caches.
- If REDIS_URL is unset, the rate limiter falls back to an in-process limiter (fine for dev) but Celery requires a real Redis broker.

Status
This is a scaffold. Network client methods are wired with rate limiting and retries but contain TODOs to complete decoding logic, price provider request/response parsing, and persistence.

Anchors (blue‑chip catalogs)
- File-backed anchors live at `config/anchors.json` (loaded automatically). Override path via `ANCHORS_FILE`.
- Classifier uses anchors to boost confidence for top protocols (Uniswap, Balancer, 1inch/0x, CoWSwap, ParaSwap, Euler, Silo v2). Add/update addresses as needed.
