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

Redis notes
- We use Redis for: Celery broker/results, rate limiting, and simple caches.
- If REDIS_URL is unset, the rate limiter falls back to an in-process limiter (fine for dev) but Celery requires a real Redis broker.

Status
This is a scaffold. Network client methods are wired with rate limiting and retries but contain TODOs to complete decoding logic, price provider request/response parsing, and persistence.
