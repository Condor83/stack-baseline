Upgraded PRD (v2): EVM Blockchain Data Warehouse
1) Executive Summary (refined)

Vision: A multichain (50+ EVM) warehouse that ingests, decodes, classifies, and prices on‑chain activity, producing accurate, explainable USD cost & P&L with real‑time wallet and protocol views.

Design tenets: determinism > heuristics; protocol‑aware decoding; layered storage; chain‑specific fee logic; reproducible math; human‑in‑the‑loop for tail cases.

2) External Providers & Endpoints (production‑ready mix)

A. Core chain data (read):

Etherscan API V2 (single API key, multichain with chainid):

Tx history: module=account&action=txlist (cap ~10k/addr; paginate by block windows)

Internal tx: module=account&action=txlistinternal (cap ~10k)

Event logs: module=logs&action=getLogs (topic filters)

Contract metadata: module=contract&action=getabi|getsourcecode

Base path: https://api.etherscan.io/v2/api?chainid=<id>&...

Rate limits by plan; Free 5 rps, Pro tiers up to 30 rps/day limits as documented.
Risks: caps, occasional lag, missing traces. Mitigation: see “Trace providers.” 
docs.etherscan.io
+3
docs.etherscan.io
+3
docs.etherscan.io
+3

Trace providers (internal calls, delegatecall trees, revert reasons):

Alchemy Trace/Debug API: trace_transaction, debug_traceTransaction, trace_replayTransaction. Budget compute‑units; use selectively for decoding/MEV. 
Alchemy
+1

Erigon/Nethermind trace RPC on chains where Alchemy isn’t available: trace_replayTransaction, trace_block. (via QuickNode/Ankr/BlockPi, etc.) 
docs.erigon.tech
QuickNode

B. Portfolio enrichment (optional):

DeBank Open API (user balances/positions): /v1/user/total_balance, /v1/user/token_list, /v1/user/portfolio_list (treat as optional; apply for access). 
DeBank Cloud

C. Prices (historical & live):

CoinGecko Pro: /coins/{id}/market_chart/range, and contract‑address routes.

DeFiLlama Prices API: tokens by chain/contract; Pro for higher limits.

Result selection: “latest price at or before tx timestamp” within 60‑sec window. 
CoinGecko API Documentation
+1
DeFi Llama API Docs

D. ABI & source:

Sourcify API v2 (first), fallback Etherscan getabi/getsourcecode, final fallback 4byte.directory signature matching + bytecode inference. Detect proxies via EIP‑1967/1167/2535 patterns. 
docs.sourcify.dev
docs.etherscan.io
4byte.directory

E. Bridges & intents:

CoWSwap settlement decoder (GPv2Settlement) and solver awareness.

LayerZero/Stargate, Across, Hop, Circle CCTP contract registries + event schemas for cross‑chain linkage. 
docs.cow.fi
stargateprotocol.gitbook.io
Across Documentation
+1
developers.circle.com

3) Architecture (revised)

3.1 High‑level

API (FastAPI)
   ↕
Job Orchestrator (Celery + Redis)  — idempotent tasks, DLQ
   ↕
Ingestion Services (Etherscan V2, Trace RPCs, Logs)
   ↕
Decoding & Classification (ABI fetcher, Proxy resolver, Event/Trace parsers)
   ↕
Analytics (Cost & P&L with chain adapters; MEV heuristics)
   ↕
Storage:
  - Postgres (Supabase) for OLTP, auth/RLS, API reads that are small
  - ClickHouse (or Timescale partitioning) for events/logs/traces & heavy analytics
  - Redis cache for hot aggregates and API responses


3.2 Storage choices

Postgres (Supabase) for canonical rows & API entities (wallets, transactions summary).

Columnar store for logs/traces (ClickHouse) or Timescale on Postgres with time + chain_id partitions. This is what unlocks <100 ms on aggregation endpoints.

Supabase Realtime for WS subscriptions (RLS‑aware). 
Supabase

3.3 Supabase connection model

Writes/long sessions: 5432 (session mode).

Serverless bursts: 6543 (transaction mode, disable prepared statements / set prepare_threshold=0). 
Supabase
+1

4) Data Model (delta to yours)

New/expanded tables (Postgres):

blocks(chain_id, number, timestamp, base_fee_per_gas, ... )

contracts(address, chain_id, proxy_type, implementation, beacon, diamond_facets, verified_source, abi_json, first_seen_block, ...)

logs(id, tx_id, log_index, address, topics[], data, decoded_event, ...) (GIN on topics)

traces(id, tx_id, trace_address[], type, from, to, input, output, value, error, action_json, result_json)

token_metadata(chain_id, address, symbol, decimals, coingecko_id, defillama_id, ...)

token_transfers (ERC20/721/1155 normalized; explode TransferBatch)

classifications(tx_id, primary_label, secondary_label, protocol, confidence, details_json)

prices(chain_id, contract, minute, price_usd)

bridge_links(src_chain_id, src_tx_hash, dst_chain_id, dst_tx_hash, protocol, message_id, status)

mev_findings(tx_id, type, severity, attacker_addr, score, details_json)

Partitioning: transactions, logs, traces, token_transfers by (chain_id, month).

5) Ingestion & Decoding

5.1 Ingestion strategy

Accounts/tokens/logs: Etherscan V2. Respect per‑plan rps + daily quota (token bucket per chain). Use block‑range paging to avoid 10k cap. 
docs.etherscan.io
+1

Traces: If classification requires internal calls (swaps via routers, multicall, delegatecall), call trace/debug (retry with exponential backoff; rate‑limit by provider CU). 
Alchemy

Receipts: Always store status + gasUsed/maxFee/baseFee. (Use gettxreceiptstatus for legacy fallback.) 
docs.etherscan.io

5.2 ABI & proxy resolution

Try Sourcify repository → fetch ABI; else Etherscan getabi; else 4byte to guess function selectors; detect proxies:

EIP‑1967 storage slots

EIP‑1167 clones (bytecode pattern)

EIP‑2535 diamonds (facet selectors)
Store final resolved ABI per (address, block_range) to handle upgrades. 
docs.sourcify.dev
docs.etherscan.io
4byte.directory

5.3 Event & trace parsing

Standards: ERC‑20 Transfer/Approval, ERC‑721 Transfer/Approval/ApprovalForAll, ERC‑1155 TransferSingle/TransferBatch. Normalize 1155 batches to rows. 
docs.openzeppelin.com
+2
docs.openzeppelin.com
+2

Multicall detection (selector 0x5ae401dc, etc.) and per‑call decode using inner traces where present.

6) Classification (rule‑first, ML‑assist)

Hierarchy (as you proposed) with detection cues:

transfers: ETH, ERC‑20/721/1155; derive internal via traces; bridge if from known bridge contracts or cross‑chain message IDs.

swaps:

DEX AMM: event combos (Pair/Pool Sync/Swap), router selectors, pool factory membership

aggregators: 1inch, 0x, Paraswap routers

CoWSwap: settlement contract calls (GPv2Settlement), solver addresses; compute actual in/out from settlement data and interactions. 
docs.cow.fi

defi: Aave/Compound/Curve/Balancer/Lido; protocol catalogs (factory/markets).

nft: mints/sales via marketplaces (Seaport/Blur/LooksRare) using standard events.

governance: Governor events; approvals incl. EIP‑2612 permits. 
docs.openzeppelin.com

Confidence scoring:

1.0 = ABI‑exact + protocol registry;

0.8 = ABI‑exact but unknown protocol;

0.6 = selector‑match + heuristics;

<0.6 routed to manual review queue (your /api/v1/classify fits perfectly).

ML model (phase 2): gradient‑boosted or small transformer over extracted features (selectors, event graph, address labels). Only to lift tail.

7) Cost & Analytics (deterministic)

7.1 Gas cost (USD)

EIP‑1559 L1 chains: effective_gas_price * gas_used * native_price_at_timestamp.

Optimism family: include l1Fee from receipt (or API) as l1_data_usd component. 
Optimism Docs

Arbitrum Nitro: compute L2 + L1 data fee per docs; use receipt fields/provider where exposed; label components. 
Arbitrum Docs

7.2 Slippage (swaps)

If a quoted price exists in input data (aggregator params), compute (usd_in - usd_out)/usd_in. Else compute against pool mid‑price at block‑time by reading pool reserves from logs just before/after the swap.

7.3 MEV

Sandwich heuristic: same block, same pool, attacker address A buys before and sells after victim’s swap, net profit positive; cluster by known builder/relay addresses; score severity. Use research patterns as reference.

7.4 Bridges

For LayerZero/Stargate, Across, Hop, CCTP: record (src_tx, dst_tx, protocol, message_id, status) with timing & fee. Contract registries from protocol docs. 
stargateprotocol.gitbook.io
Across Documentation
+1
developers.circle.com

7.5 P&L / cost basis

FIFO default; lot‑aware per token; realized P&L on swaps/transfers to external; unrealized via end‑of‑day prices per wallet.

8) API & Real‑time (polished)

REST (unchanged paths), plus:

/api/v1/tx/{hash}: decoded call tree, events, costs, MEV flags.

/api/v1/wallets/{addr}/portfolio: holdings, positions, P&L snapshot (Debank‑enriched if available).

/api/v1/analytics/...: pre‑aggregated views; all endpoints must hit pre‑computed tables or Redis.

Realtime:

Supabase Realtime channels per wallet and per protocol; all streams respect RLS. 
Supabase
+1

Auth & quotas:
JWT/JWE with per‑key rps; 429 with Retry-After.

9) Workers & Job Management (hardened)

Idempotency keys on tasks (wallet+chain+block range).

Priority queues: user‑triggered recent activity > backfills > ML training.

DLQ + replays with jitter; circuit breakers on providers; cost guardrails on trace/debug CUs.

Observability: Prometheus + Grafana; Sentry; OpenTelemetry spans for “ingest → decode → classify → cost.”

10) Quality, Datasets & SLAs

Golden set of ~2–3k tx hashes spanning: ERC‑20/721/1155; AMMs (UniV2/V3, Sushi, Curve), aggregators (1inch/0x/Para), CoWSwap, bridges (LZ/Stargate, Across, Hop, CCTP), staking (Lido), lending (Aave/Compound), multicall, proxies/upgrades, failed tx, sandwiches.

Targets (v1):

Decode coverage ≥99% on golden set;

Classification accuracy ≥97% overall, ≥99% on top 20 protocols;

USD cost error ≤1% median, ≤2% p95;

API p95 latency <150 ms for cached/pre‑aggregated endpoints; <100 ms goal for hot paths.

Load tests: 10k tx/min ingest & process; 5k rps cached reads; 200 rps uncached reads.

11) Parallel Tracks (agents) — refined

Track A – Core Infra (Agent 1): project scaffolding, DBs (Postgres + ClickHouse optional), Alembic, logging, OpenTelemetry, Supabase dual‑port configs with prepared‑statements disabled on 6543. Exit: migrations run; healthchecks up. 
Supabase

Track B – Ingestion (Agent 2): Etherscan V2 client (rps controller, block‑window paginator, 10k cap safe), Trace providers (Alchemy/Erigon), ABI fetchers (Sourcify→Etherscan→4byte). Exit: end‑to‑end tx fetch for 8 chains. 
docs.etherscan.io
Alchemy
docs.sourcify.dev

Track C – Decoding & Classifier (Agent 3): proxy resolver (EIP‑1967/1167/2535), event & trace parsers, rule‑based classifier, CoWSwap & bridges handlers. Exit: ≥95% accuracy on golden set. 
docs.cow.fi

Track D – Cost & Analytics (Agent 4): chain adapters (OP/ARB), PriceService (CG/Llama), slippage & MEV heuristics; aggregation jobs with caching. Exit: ≤1–2% cost error p95 on golden set. 
Optimism Docs
Arbitrum Docs
CoinGecko API Documentation

Track E – API & Realtime (Agent 5): REST/WS, RLS policies, rate limiting, OpenAPI docs, integration tests.

(Optional) Agent 6 – Evaluator: auto‑diff classifications vs. ground truth; triages low‑confidence cases to the manual endpoint; produces weekly confusion matrices.

12) Database DDL (delta to yours; exemplar)
-- partitions recommended in DDL generator (by chain_id, month)

CREATE TABLE contracts (
  address        bytea NOT NULL,
  chain_id       integer NOT NULL,
  proxy_type     text,                 -- 'EIP1967'|'EIP1167'|'EIP2535'|NULL
  implementation bytea,
  beacon         bytea,
  verified_source boolean DEFAULT false,
  abi_json       jsonb,
  first_seen_block bigint,
  updated_at     timestamptz DEFAULT now(),
  PRIMARY KEY(chain_id, address)
);

CREATE TABLE logs (
  id bigserial PRIMARY KEY,
  tx_id bigint REFERENCES transactions(id) ON DELETE CASCADE,
  log_index integer,
  address bytea,
  topics bytea[],
  data bytea,
  decoded_event jsonb
);
CREATE INDEX idx_logs_addr ON logs(address);
CREATE INDEX idx_logs_topics ON logs USING gin(topics);

CREATE TABLE traces (
  id bigserial PRIMARY KEY,
  tx_id bigint REFERENCES transactions(id) ON DELETE CASCADE,
  trace_address integer[],
  type text,
  "from" bytea,
  "to" bytea,
  input bytea,
  output bytea,
  value numeric(78,0),
  error text,
  action_json jsonb,
  result_json jsonb
);


(Retain your existing transactions, token_transfers, token_prices with added partitioning & indexes.)

13) Monitoring & Runbooks (practical)

Provider budget guards: stop‑gap if Etherscan X-RateLimit-Remaining < threshold; spillover after 5 mins.

Trace spending cap: per‑day CU budget; fall back to best‑effort decode.

Data quality alerts: spike in “unclassified” >1% or cost deviation drift >2% triggers paging.

Attribution: if you use free Etherscan endpoints, ensure attribution (“Powered by Etherscan”) where applicable. 
docs.etherscan.io

14) Phasing & Confidence

Phase 1 (Weeks 1–2): Tracks A–D skeletons + 8‑chain MVP (ETH, Arbitrum 42161, Optimism 10, Base 8453, Polygon 137, BSC 56, Avalanche 43114, zkSync 324). Why these: high volume + require diverse fee adapters. 
docs.base.org
Arbitrum Docs
chainlist.org
+1

Phase 2 (Weeks 3–4): API + Realtime; golden‑set QA; cost validation (OP/ARB).

Phase 3 (Week 5+): Backfill + ML assist + more chains via Etherscan V2 chainid.

Confidence uplift: With the provider mix, chain‑specific fee adapters, and robust ABI/proxy resolution, the riskiest failure modes are covered. The remaining risk is provider quota/cost, which is controlled via budgets and DLQs.

Concrete “to‑build” Checklists

Etherscan V2 client

Base URL /v2/api, chainid param, retry on 429 with jitter, token‑bucket limiter per plan. Block‑window paginator to avoid 10k cap on txlist/txlistinternal. 
docs.etherscan.io
+1

Trace client

Alchemy trace_transaction/debug_traceTransaction; fallback to node endpoints (Erigon). Meter compute units. 
Alchemy

Price service

CG /market_chart/range (contract‑address route for tokens) → Redis minute cache → Llama fallback. 
CoinGecko API Documentation
+1

Fees

OP adapter reads l1Fee (receipt), ARB adapter computes L1 + L2 per docs / provider. 
Optimism Docs
Arbitrum Docs

CoWSwap

Detect calls to GPv2Settlement and compute actual swap in/out from settlement interactions; solver tagging. 
docs.cow.fi

Bridges

Contract registries for LayerZero/Stargate, Across, Hop, CCTP; message‑ID link table. 
stargateprotocol.gitbook.io
Across Documentation
+1
developers.circle.com

Supabase

Use 5432 for async workers (session mode), 6543 for serverless edges with prepared statements disabled in client. Enable RLS on user‑facing tables; Realtime channels for wallets. 
Supabase
+1

Final notes on scope & metrics

The original “99.9% classification accuracy” is not realistic across all long‑tail contracts without a human‑in‑the‑loop and ML assist. I’ve set tiered targets (≥97% overall, ≥99% top protocols) with a golden set to prove it.

The “<100 ms” goal is feasible on cached/pre‑aggregated endpoints; for raw log queries, plan ClickHouse/Timescale or precompute.