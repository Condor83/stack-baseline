ALTER TABLE transactions
  ADD COLUMN IF NOT EXISTS method_id bytea,
  ADD COLUMN IF NOT EXISTS function_name text;

