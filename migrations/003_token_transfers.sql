CREATE TABLE IF NOT EXISTS token_transfers (
  id bigserial PRIMARY KEY,
  chain_id integer NOT NULL,
  tx_id bigint NOT NULL,
  log_index integer,
  token_address bytea NOT NULL,
  from_address bytea,
  to_address bytea,
  standard varchar(16) NOT NULL,
  value numeric(78,0),
  token_id numeric(78,0)
);

