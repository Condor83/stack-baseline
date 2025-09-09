-- Migrated from migrations/004_internal_transactions.sql

CREATE TABLE IF NOT EXISTS internal_transactions (
  id bigserial PRIMARY KEY,
  tx_id bigint,
  trace_id varchar(128),
  type varchar(32),
  from_address bytea,
  to_address bytea,
  value numeric(78,0),
  contract_address bytea,
  is_error integer,
  error_code varchar(128),
  gas bigint,
  gas_used bigint
);

