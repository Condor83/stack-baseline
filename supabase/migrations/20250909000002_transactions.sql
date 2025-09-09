-- Migrated from migrations/002_transactions.sql

CREATE TABLE IF NOT EXISTS transactions (
  id bigserial PRIMARY KEY,
  chain_id integer NOT NULL,
  hash bytea NOT NULL,
  block_number bigint,
  block_hash bytea,
  transaction_index integer,
  from_address bytea,
  to_address bytea,
  value numeric(78,0),
  input bytea,
  nonce bigint,
  gas bigint,
  gas_price numeric(78,0),
  max_fee_per_gas numeric(78,0),
  max_priority_fee_per_gas numeric(78,0),
  status integer,
  gas_used bigint,
  effective_gas_price numeric(78,0),
  timestamp bigint,
  UNIQUE(chain_id, hash)
);

