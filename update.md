EVM Decoder – Progress Update

Date: 2025-09-09

Overview
- Reviewed PRD in AGENTS.md and aligned architecture, providers, data model, and targets.
- Scaffolded a production-oriented service with FastAPI + Celery workers, Redis rate limiting, Postgres persistence, and Supabase migrations.

Services & Workers
- FastAPI app with health and validation endpoints.
- Celery workers with queues: `ingest`, `decode`, `prices`, `analytics`.
- Redis-backed token-bucket limiter with fractional RPS support (e.g., 0.5 rps).

Ingestion (Track B)
- Etherscan V2 client:
  - `txlist` with block-window pagination.
  - `txlistinternal` for internal txs.
  - `logs.getLogs` (used selectively; primary logs now via receipts).
  - Proxy `eth_getTransactionReceipt` to persist per-tx logs and receipt fields.
  - `block.getblocknobytime` to map date/time → block.
  - Resilient handling for “no data” responses and hex/decimal numeric parsing.
- Persistence (SQLAlchemy + psycopg3):
  - `transactions` (upsert on `(chain_id, hash)`), updates from receipts: `status`, `gas_used`, `effective_gas_price`.
  - `logs` with `decoded_event` as JSONB (placeholder null for now).
  - `token_transfers` from receipt logs (ERC-20 value, ERC-721 tokenId).
  - `internal_transactions` from `txlistinternal`.
- API triggers:
  - `POST /api/v1/ingest/address` (block window)
  - `POST /api/v1/ingest/address_by_date` (date window → block window)

Validation Endpoints
- `GET /api/v1/address/{chain_id}/{address}/summary` (counts + block range)
- `GET /api/v1/address/{chain_id}/{address}/transactions` (paginated)
- `GET /api/v1/address/{chain_id}/{address}/logs` (topic0 surfaced)
- `GET /api/v1/address/{chain_id}/{address}/token_transfers` (ERC-20/721)
- Task status: `GET /api/v1/tasks/{task_id}`
- Smoke script: `python scripts/smoke_api.py <address> --chain-id 1 --from-block X --to-block Y --ingest`

Pricing
- PriceService with provider order: CoinGecko → DeFiLlama → (budgeted Alchemy placeholder).
- Supports CoinGecko free/demo (`x_cg_demo_api_key` query) and Pro (header + pro host).
- Minute bucketing with ±60s window and Redis caching.
- Endpoint: `GET /api/v1/price/{chain_id}/{contract}?ts=` (supports `native`).

Supabase & Migrations
- SQL migrations mirrored under `supabase/migrations/` with proper timestamps:
  - `...000001_init.sql` (core tables)
  - `...000002_transactions.sql`
  - `...000003_token_transfers.sql`
  - `...000004_internal_transactions.sql`
- README includes Supabase CLI workflow. Local DB URL uses `postgresql+psycopg` driver.

DevOps & Setup
- Redis via Docker Compose on host port `6380` (avoid 6379 conflicts).
- Pydantic v2 + pydantic-settings; extra env ignored; RPS as floats.
- Git initialized on `main`, remote added; .gitignore in place.

Notable Fixes During Session
- Adjusted for Pydantic v2 import changes.
- Resolved Redis port conflict and updated env defaults.
- Fractional RPS limiting and robust int parsing for hex fields (e.g., `0xb0`).
- Treated Etherscan “no data” responses as non-errors.
- Guarded receipt parsing when `result` is not an object.

Open Items / Next Steps
- ERC-1155 TransferSingle/TransferBatch normalization.
- Alchemy trace worker: per-chain hosts, strict daily budget, and selective usage.
- Cost adapters (OP/ARB L1 data fee) and analytics endpoints.
- ABI fetchers (Sourcify→Etherscan→4byte), proxy resolver, core decoders.
- Indexing/partitioning for hot tables; RLS policies; Realtime channels.
- Integration tests and a small golden set for validation.

How to Use (quick)
- Start Redis: `docker compose up -d redis` (REDIS_URL default `redis://localhost:6380/0`).
- Run API: `uvicorn evm_decoder.api.main:app --reload`.
- Run workers: `celery -A evm_decoder.celery_app.celery_app worker -Q ingest -l info` (others optional).
- Ingest by date: `POST /api/v1/ingest/address_by_date` with `{ chain_id, address, start, end }`.
- Validate: use the address summary/transactions/logs/token_transfers endpoints.
