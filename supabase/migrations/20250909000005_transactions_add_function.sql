-- Add function metadata columns for Etherscan txlist enrichment
ALTER TABLE transactions
  ADD COLUMN IF NOT EXISTS method_id bytea,
  ADD COLUMN IF NOT EXISTS function_name text;

