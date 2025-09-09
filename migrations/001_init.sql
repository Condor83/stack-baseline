-- Exemplar DDL based on PRD; adapt as needed.

CREATE TABLE IF NOT EXISTS contracts (
  address        bytea NOT NULL,
  chain_id       integer NOT NULL,
  proxy_type     text,
  implementation bytea,
  beacon         bytea,
  verified_source boolean DEFAULT false,
  abi_json       jsonb,
  first_seen_block bigint,
  updated_at     timestamptz DEFAULT now(),
  PRIMARY KEY(chain_id, address)
);

CREATE TABLE IF NOT EXISTS logs (
  id bigserial PRIMARY KEY,
  tx_id bigint,
  log_index integer,
  address bytea,
  topics bytea[],
  data bytea,
  decoded_event jsonb
);
CREATE INDEX IF NOT EXISTS idx_logs_addr ON logs(address);
CREATE INDEX IF NOT EXISTS idx_logs_topics ON logs USING gin(topics);

CREATE TABLE IF NOT EXISTS traces (
  id bigserial PRIMARY KEY,
  tx_id bigint,
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

-- Additional canonical tables (sketch)
CREATE TABLE IF NOT EXISTS blocks (
  chain_id integer NOT NULL,
  number bigint NOT NULL,
  timestamp timestamptz NOT NULL,
  base_fee_per_gas numeric(78,0),
  PRIMARY KEY(chain_id, number)
);

CREATE TABLE IF NOT EXISTS token_metadata (
  chain_id integer NOT NULL,
  address bytea NOT NULL,
  symbol text,
  decimals integer,
  coingecko_id text,
  defillama_id text,
  updated_at timestamptz DEFAULT now(),
  PRIMARY KEY(chain_id, address)
);

CREATE TABLE IF NOT EXISTS classifications (
  tx_id bigint PRIMARY KEY,
  primary_label text,
  secondary_label text,
  protocol text,
  confidence numeric(3,2),
  details_json jsonb
);

CREATE TABLE IF NOT EXISTS prices (
  chain_id integer NOT NULL,
  contract bytea NOT NULL,
  minute timestamptz NOT NULL,
  price_usd numeric,
  PRIMARY KEY(chain_id, contract, minute)
);

CREATE TABLE IF NOT EXISTS bridge_links (
  src_chain_id integer,
  src_tx_hash bytea,
  dst_chain_id integer,
  dst_tx_hash bytea,
  protocol text,
  message_id text,
  status text,
  PRIMARY KEY (src_chain_id, src_tx_hash, dst_chain_id, dst_tx_hash)
);

CREATE TABLE IF NOT EXISTS mev_findings (
  tx_id bigint PRIMARY KEY,
  type text,
  severity text,
  attacker_addr bytea,
  score numeric(4,2),
  details_json jsonb
);

