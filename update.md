EVM Decoder – Progress Update

Date: 2025-09-09

Overview
- Reviewed PRD in AGENTS.md and aligned architecture, providers, data model, and targets.
- Scaffolded a production-grade service: FastAPI + Celery workers, Redis rate limiting, Postgres persistence, Supabase migrations.

Services & Workers
- FastAPI endpoints: health, ingest triggers, task status, validation views, price, tx view.
- Celery queues: `ingest`, `decode`, `prices`, `analytics`.
- Redis‑backed token‑bucket limiter (supports fractional RPS).

Ingestion
- Etherscan V2 client:
  - Account txs (`txlist`) and internal txs (`txlistinternal`) with page‑based pagination over date‑derived block ranges (no block scanning).
  - Receipts via proxy `eth_getTransactionReceipt` (status, gasUsed, effectiveGasPrice, logs).
  - Date→block via `block.getblocknobytime` (clamped to now; graceful fallbacks on “future” timestamps).
  - Robust handling for hex/decimal numeric fields and “no data” responses.
- Persistence:
  - `transactions`: upsert on (chain_id, hash); updates from receipts; stores `method_id` and `function_name` from txlist.
  - `logs`: raw + `decoded_event` (jsonb) for decoded events.
  - `token_transfers`: ERC‑20/721/1155 (Single/Batch) from receipt logs.
  - `internal_transactions`: from `txlistinternal`.
- Progress: ingest task emits progress meta (pages, txs, receipts, logs, transfers); CLI shows live hints while waiting.

Decoding & Classification
- ABI resolution (proxy‑aware): Sourcify → Etherscan getabi; if proxy via getsourcecode, resolve implementation ABI; cache in `contracts` with `proxy_type`, `implementation`, `verified_source`.
- ABI‑based call decoding with 4byte fallback for selector names; ABI‑based event decoding stored in `logs.decoded_event`.
- Classifier: agnostic rules (topics/flows/functionName/methodId) + anchors (routers/vault/settlement) from file‑backed catalog.
  - Blue‑chip anchors seeded for ETH and OP (Uniswap v2/v3, 1inch, 0x, CoWSwap, Balancer Vault, ParaSwap, Euler factory, Silo factory/router); easy to extend via `config/anchors.json` or `ANCHORS_FILE`.
  - Added rules: Balancer (swap/liquidity), ParaSwap (swap variants), Aave (deposit/withdraw/borrow/repay), Uniswap routers, CoWSwap, 1inch/0x, Euler/Silo cues.
- Classification persisted in `classifications` with confidence and details (includes cost + decoded_call).

Pricing & Costs
- PriceService: CoinGecko → DeFiLlama with Redis cache; now reads/writes `prices` table (minute buckets).
- Gas USD cost computed for L1 (EIP‑1559) and included in classification details.
- OP/ARB fee components deferred (to be added in a later PR).

API & CLI
- Ingest triggers: `POST /api/v1/ingest/address_by_date` (recommended), `POST /api/v1/ingest/address` (power users).
- Validation: summary/transactions/logs/token_transfers; task status with progress.
- Price: `GET /api/v1/price/{chain_id}/{contract}?ts=` (supports native).
- Tx view: `GET /api/v1/tx/{hash}` returns tx info + classification + up to 5 decoded events + decoded_call (ABI/4byte best‑effort).
- Decode/traces: `POST /api/v1/decode/{chain_id}/{tx_hash}` (decode), `POST /api/v1/traces/{chain_id}/{tx_hash}` (budgeted traces).
- CLI: interactive menu (`shell`), date‑based ingest, pipeline (ingest + optional traces), waitable `tx --wait-decode`, plus summary/txs/logs/transfers/price.

Supabase & Migrations
- Timestamped migrations under `supabase/migrations/`:
  - Core schema (`...000001_init.sql`), transactions (`...000002_transactions.sql`), token_transfers (`...000003_token_transfers.sql`), internal_transactions (`...000004_internal_transactions.sql`), tx function metadata (`...000005_transactions_add_function.sql`).

DevOps & Setup
- Redis on host port 6380; `.env.example` configured; fractional RPS envs.
- Pydantic v2 + pydantic‑settings; extra env ignored; anchors via JSON file.
- Git repo initialized; PR branch active (`pr/track-b-aug2025-ingest`).

Key Fixes
- Pydantic v2 migration; rate limit parsing (floats); Redis port conflict fix.
- Etherscan “future timestamp” and “no data” handled gracefully.
- Hex parsing for numeric fields from Etherscan logs (e.g., `0xb0`).
- Classification + decoding work without L2 fee dependencies.

How to Use (quick)
- Start Redis: `docker compose up -d redis`.
- API: `uvicorn evm_decoder.api.main:app --reload`.
- Workers: `celery -A evm_decoder.celery_app.celery_app worker -Q ingest -l info` and `-Q decode -l info`.
- CLI examples:
  - Ingest by date: `python3 -m evm_decoder.cli ingest-by-date --chain-id 1 --address 0x... --start-date 2025-08-01 --end-date 2025-08-31 --wait`
  - Tx decode: `python3 -m evm_decoder.cli tx --chain-id 1 --tx-hash 0x... --wait-decode`
  - Interactive: `python3 -m evm_decoder.cli shell`

Next Phase – Detailed TODO
1) ABI & Proxies (finish)
   - Add Redis memo for ABI lookups; cache negative results briefly.
   - Persist `proxy_type` variants (EIP‑1167 clones, EIP‑2535 diamonds) when detectable; store facets list for diamonds if available.
   - Add “ABI range” support (address, block_start, block_end) to handle upgrades over time.

2) Protocol Rules & Discovery
   - Aave: add anchors (Pool/LendingPool mainnet); refine rules for v2/v3 events.
   - Balancer: add pool discovery via Vault events (optional); classify join/exit vs swap more precisely.
   - ParaSwap/0x/1inch: selector catalogs for common entrypoints; decode calldata structure (best‑effort).
   - Uniswap: optional factory event ingestion (PairCreated/PoolCreated) to tag pools by factory provenance.
   - Bridges (Phase 2): minimal anchors (LZ/Stargate/Across/Hop/CCTP) and link table population.

3) Costs & Prices
   - Persist price source; expose `/api/v1/tx/{hash}` cost breakdown (components + source).
   - Add OP/ARB adapters (L1 data fee) in a separate PR; include labeled components in result.
   - Add price warmer job (minute buckets) for tokens seen in a date range.

4) API & CLI Polish
   - `/api/v1/tx/{hash}`: include decoded_call args (already); add a “full decoded events” endpoint.
   - CLI: add `anchors` command to list anchors per chain; add `tx --full-events` to fetch all decoded events.
   - Add `/api/v1/address/{chain_id}/{address}/tokens` summary (balances via transfers net, optional DeBank enrich).

5) Indexing & Performance
   - Indexes: transactions(chain_id, block_number), transactions(method_id), logs(tx_id, log_index), token_transfers(token_address), token_transfers(from_address), token_transfers(to_address).
   - Optional partitioning by (chain_id, month) for `transactions`, `logs`, `token_transfers`.

6) Observability & Ops
   - Structured logging with request/task IDs; add minimal Prometheus counters.
   - Expose provider budgets in Redis (Etherscan/CG/Llama/traces); CLI status to show remaining budgets.
   - Idempotency keys on ingest tasks; DLQ/retry policies with jitter.

7) QA
   - Curate a mini golden set (50–100 txs) across swaps/aggregators/lending/NFT; add a script to compute coverage and classification accuracy.
   - Integration tests for API endpoints and CLI flows (offline mocks where possible).
