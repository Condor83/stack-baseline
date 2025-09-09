from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection


metadata = MetaData()


transactions = Table(
    "transactions",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("chain_id", Integer, nullable=False),
    Column("hash", LargeBinary, nullable=False),
    Column("block_number", BigInteger),
    Column("block_hash", LargeBinary),
    Column("transaction_index", Integer),
    Column("from_address", LargeBinary),
    Column("to_address", LargeBinary),
    Column("value", Numeric(78, 0)),
    Column("input", LargeBinary),
    Column("nonce", BigInteger),
    Column("gas", BigInteger),
    Column("gas_price", Numeric(78, 0)),
    Column("max_fee_per_gas", Numeric(78, 0)),
    Column("max_priority_fee_per_gas", Numeric(78, 0)),
    Column("status", Integer),
    Column("gas_used", BigInteger),
    Column("effective_gas_price", Numeric(78, 0)),
    Column("timestamp", BigInteger),
    UniqueConstraint("chain_id", "hash", name="uq_transactions_chain_hash"),
)


logs = Table(
    "logs",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("tx_id", BigInteger),
    Column("log_index", Integer),
    Column("address", LargeBinary),
    Column("topics", LargeBinary),  # we will pack as JSON-like bytes or concat; see helpers
    Column("data", LargeBinary),
    Column("decoded_event", Text),
)


def _hex_to_bytes(x: Optional[str]) -> Optional[bytes]:
    if x is None:
        return None
    if isinstance(x, str) and x.startswith("0x"):
        try:
            return bytes.fromhex(x[2:])
        except Exception:
            return None
    return None


def _topics_to_bytes(topics: Optional[List[str]]) -> Optional[bytes]:
    if not topics:
        return None
    try:
        # Store topics as concatenated 32-byte entries with simple delimiter "|" between hex'ified topics.
        # This is a temporary packing until we implement a proper bytea[] via psycopg dialect operations.
        return ("|".join(t.lower() for t in topics)).encode()
    except Exception:
        return None


def upsert_transaction(conn: Connection, chain_id: int, tx: Dict[str, Any]) -> Optional[int]:
    values = {
        "chain_id": chain_id,
        "hash": _hex_to_bytes(tx.get("hash")),
        "block_number": int(tx.get("blockNumber")) if tx.get("blockNumber") else None,
        "block_hash": _hex_to_bytes(tx.get("blockHash")),
        "transaction_index": int(tx.get("transactionIndex")) if tx.get("transactionIndex") else None,
        "from_address": _hex_to_bytes(tx.get("from")),
        "to_address": _hex_to_bytes(tx.get("to")),
        "value": int(tx.get("value")) if tx.get("value") else None,
        "input": _hex_to_bytes(tx.get("input")),
        "nonce": int(tx.get("nonce")) if tx.get("nonce") else None,
        "gas": int(tx.get("gas")) if tx.get("gas") else None,
        "gas_price": int(tx.get("gasPrice")) if tx.get("gasPrice") else None,
        "max_fee_per_gas": int(tx.get("maxFeePerGas")) if tx.get("maxFeePerGas") else None,
        "max_priority_fee_per_gas": int(tx.get("maxPriorityFeePerGas")) if tx.get("maxPriorityFeePerGas") else None,
        "status": int(tx.get("txreceipt_status")) if tx.get("txreceipt_status") else None,
        "gas_used": int(tx.get("gasUsed")) if tx.get("gasUsed") else None,
        "effective_gas_price": int(tx.get("effectiveGasPrice")) if tx.get("effectiveGasPrice") else None,
        "timestamp": int(tx.get("timeStamp")) if tx.get("timeStamp") else None,
    }
    stmt = insert(transactions).values(**values).on_conflict_do_nothing(index_elements=[transactions.c.chain_id, transactions.c.hash])
    res = conn.execute(stmt)
    if res.inserted_primary_key is not None and len(res.inserted_primary_key) > 0:
        return int(res.inserted_primary_key[0])
    # Fetch existing id
    sel = select(transactions.c.id).where(
        transactions.c.chain_id == chain_id, transactions.c.hash == values["hash"]
    )
    row = conn.execute(sel).fetchone()
    return int(row[0]) if row else None


def insert_logs_for_tx(conn: Connection, tx_id: int, logs_payload: List[Dict[str, Any]]):
    rows = []
    for l in logs_payload:
        if int(l.get("logIndex", 0)) < 0:
            continue
        rows.append(
            {
                "tx_id": tx_id,
                "log_index": int(l.get("logIndex")),
                "address": _hex_to_bytes(l.get("address")),
                "topics": _topics_to_bytes(l.get("topics")),
                "data": _hex_to_bytes(l.get("data")),
                "decoded_event": None,
            }
        )
    if not rows:
        return 0
    conn.execute(insert(logs), rows)
    return len(rows)
