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
    delete,
    select,
)
from sqlalchemy.dialects.postgresql import insert, JSONB
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
    Column("method_id", LargeBinary),
    Column("function_name", Text),
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
    Column("decoded_event", JSONB),
)


token_transfers = Table(
    "token_transfers",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("chain_id", Integer, nullable=False),
    Column("tx_id", BigInteger, nullable=False),
    Column("log_index", Integer, nullable=True),
    Column("token_address", LargeBinary, nullable=False),
    Column("from_address", LargeBinary, nullable=True),
    Column("to_address", LargeBinary, nullable=True),
    Column("standard", String(16), nullable=False),  # 'erc20' | 'erc721' | 'erc1155'
    Column("value", Numeric(78, 0), nullable=True),
    Column("token_id", Numeric(78, 0), nullable=True),
)


internal_txs = Table(
    "internal_transactions",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("tx_id", BigInteger, nullable=True),
    Column("trace_id", String(128), nullable=True),
    Column("type", String(32), nullable=True),
    Column("from_address", LargeBinary, nullable=True),
    Column("to_address", LargeBinary, nullable=True),
    Column("value", Numeric(78, 0), nullable=True),
    Column("contract_address", LargeBinary, nullable=True),
    Column("is_error", Integer, nullable=True),
    Column("error_code", String(128), nullable=True),
    Column("gas", BigInteger, nullable=True),
    Column("gas_used", BigInteger, nullable=True),
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


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        v = value.strip()
        try:
            if v.startswith("0x") or v.startswith("0X"):
                return int(v, 16)
            return int(v)
        except Exception:
            return None
    return None


def upsert_transaction(conn: Connection, chain_id: int, tx: Dict[str, Any]) -> Optional[int]:
    values = {
        "chain_id": chain_id,
        "hash": _hex_to_bytes(tx.get("hash")),
        "block_number": _parse_int(tx.get("blockNumber")),
        "block_hash": _hex_to_bytes(tx.get("blockHash")),
        "transaction_index": _parse_int(tx.get("transactionIndex")),
        "from_address": _hex_to_bytes(tx.get("from")),
        "to_address": _hex_to_bytes(tx.get("to")),
        "value": _parse_int(tx.get("value")),
        "input": _hex_to_bytes(tx.get("input")),
        "method_id": _hex_to_bytes(tx.get("methodId")),
        "function_name": tx.get("functionName"),
        "nonce": _parse_int(tx.get("nonce")),
        "gas": _parse_int(tx.get("gas")),
        "gas_price": _parse_int(tx.get("gasPrice")),
        "max_fee_per_gas": _parse_int(tx.get("maxFeePerGas")),
        "max_priority_fee_per_gas": _parse_int(tx.get("maxPriorityFeePerGas")),
        "status": _parse_int(tx.get("txreceipt_status")),
        "gas_used": _parse_int(tx.get("gasUsed")),
        "effective_gas_price": _parse_int(tx.get("effectiveGasPrice")),
        "timestamp": _parse_int(tx.get("timeStamp")),
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
        li = _parse_int(l.get("logIndex"))
        if li is None:
            continue
        rows.append(
            {
                "tx_id": tx_id,
                "log_index": li,
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


def _topic_to_address(topic_hex: str) -> Optional[bytes]:
    if not topic_hex or not isinstance(topic_hex, str):
        return None
    if topic_hex.startswith("0x"):
        topic_hex = topic_hex[2:]
    if len(topic_hex) < 40:
        return None
    try:
        return bytes.fromhex(topic_hex[-40:])
    except Exception:
        return None


ERC_TRANSFER_SIG = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def insert_token_transfers_from_logs(
    conn: Connection, chain_id: int, tx_id: int, logs_payload: List[Dict[str, Any]]
) -> int:
    rows = []
    for l in logs_payload:
        topics = l.get("topics") or []
        if not topics:
            continue
        topic0 = topics[0].lower() if isinstance(topics[0], str) else None
        addr = _hex_to_bytes(l.get("address"))
        li = _parse_int(l.get("logIndex"))
        if addr is None:
            continue
        # ERC-20/721 share the same Transfer(...) signature
        if topic0 == ERC_TRANSFER_SIG:
            if len(topics) == 3:
                # ERC-20 Transfer(address,address,uint256) value in data
                from_addr = _topic_to_address(topics[1])
                to_addr = _topic_to_address(topics[2])
                value = _parse_int(l.get("data"))
                rows.append(
                    {
                        "chain_id": chain_id,
                        "tx_id": tx_id,
                        "log_index": li,
                        "token_address": addr,
                        "from_address": from_addr,
                        "to_address": to_addr,
                        "standard": "erc20",
                        "value": value,
                        "token_id": None,
                    }
                )
            elif len(topics) == 4:
                # ERC-721 Transfer(address,address,uint256) tokenId in topic3, no data
                from_addr = _topic_to_address(topics[1])
                to_addr = _topic_to_address(topics[2])
                token_id = _parse_int(topics[3])
                rows.append(
                    {
                        "chain_id": chain_id,
                        "tx_id": tx_id,
                        "log_index": li,
                        "token_address": addr,
                        "from_address": from_addr,
                        "to_address": to_addr,
                        "standard": "erc721",
                        "value": None,
                        "token_id": token_id,
                    }
                )
            continue
        # ERC-1155 TransferSingle/TransferBatch detection by data payload patterns
        data_hex = l.get("data")
        if isinstance(data_hex, str) and data_hex.startswith("0x"):
            dbytes = bytes.fromhex(data_hex[2:])
            # Topics len 4, data size == 64 -> TransferSingle
            if len(topics) == 4 and len(dbytes) == 64:
                from_addr = _topic_to_address(topics[2])
                to_addr = _topic_to_address(topics[3])
                token_id = int.from_bytes(dbytes[0:32], byteorder="big")
                value = int.from_bytes(dbytes[32:64], byteorder="big")
                rows.append(
                    {
                        "chain_id": chain_id,
                        "tx_id": tx_id,
                        "log_index": li,
                        "token_address": addr,
                        "from_address": from_addr,
                        "to_address": to_addr,
                        "standard": "erc1155",
                        "value": value,
                        "token_id": token_id,
                    }
                )
            # Topics len 4, data encodes two dynamic arrays: ids and values
            elif len(topics) == 4 and len(dbytes) >= 128:
                try:
                    # Parse simple ABI dynamic arrays: [offset_ids][offset_vals] then arrays at offsets
                    def read_u256(off):
                        return int.from_bytes(dbytes[off:off+32], "big")

                    off_ids = read_u256(0)
                    off_vals = read_u256(32)
                    # ids array
                    n_ids = read_u256(off_ids)
                    ids = [read_u256(off_ids + 32 + i * 32) for i in range(n_ids)]
                    # values array
                    n_vals = read_u256(off_vals)
                    vals = [read_u256(off_vals + 32 + i * 32) for i in range(n_vals)]
                    n = min(len(ids), len(vals))
                    from_addr = _topic_to_address(topics[2])
                    to_addr = _topic_to_address(topics[3])
                    for i in range(n):
                        rows.append(
                            {
                                "chain_id": chain_id,
                                "tx_id": tx_id,
                                "log_index": li,
                                "token_address": addr,
                                "from_address": from_addr,
                                "to_address": to_addr,
                                "standard": "erc1155",
                                "value": int(vals[i]),
                                "token_id": int(ids[i]),
                            }
                        )
                except Exception:
                    pass
    if not rows:
        return 0
    conn.execute(insert(token_transfers), rows)
    return len(rows)


def refresh_traces_for_tx(conn: Connection, tx_id: int, chain_id: int, tx_hash: bytes, traces_payload: List[Dict[str, Any]]) -> int:
    # Remove existing traces for the tx_id and insert new ones
    conn.execute(delete(traces).where(traces.c.tx_id == tx_id))
    rows = []
    for t in traces_payload or []:
        # action/result fields are provider-specific; keep full json in *_json columns
        action = t.get("action", {}) if isinstance(t, dict) else {}
        result = t.get("result", {}) if isinstance(t, dict) else {}
        typ = t.get("type")
        trace_addr = t.get("traceAddress") or []
        if isinstance(trace_addr, list):
            trace_address = [int(x) for x in trace_addr if isinstance(x, (int, str)) and str(x).isdigit()]
        else:
            trace_address = None
        from_b = _hex_to_bytes(action.get("from")) if isinstance(action, dict) else None
        to_b = _hex_to_bytes(action.get("to")) if isinstance(action, dict) else None
        input_b = _hex_to_bytes(action.get("input")) if isinstance(action, dict) else None
        output_b = _hex_to_bytes(result.get("output")) if isinstance(result, dict) else None
        value_i = _parse_int(action.get("value")) if isinstance(action, dict) else None
        err = t.get("error")
        rows.append(
            {
                "tx_id": tx_id,
                "trace_address": trace_address,
                "type": typ,
                "from": from_b,
                "to": to_b,
                "input": input_b,
                "output": output_b,
                "value": value_i,
                "error": err,
                "action_json": action if isinstance(action, dict) else None,
                "result_json": result if isinstance(result, dict) else None,
            }
        )
    if rows:
        conn.execute(insert(traces), rows)
    return len(rows)


def update_transaction_receipt_fields(
    conn: Connection, chain_id: int, tx_hash: bytes, status: Optional[int], gas_used: Optional[int], effective_gas_price: Optional[int]
) -> None:
    from sqlalchemy import update
    stmt = (
        update(transactions)
        .where(transactions.c.chain_id == chain_id, transactions.c.hash == tx_hash)
        .values(status=status, gas_used=gas_used, effective_gas_price=effective_gas_price)
    )
    conn.execute(stmt)
contracts = Table(
    "contracts",
    metadata,
    Column("address", LargeBinary, primary_key=True),
    Column("chain_id", Integer, primary_key=True),
    Column("proxy_type", String),
    Column("implementation", LargeBinary),
    Column("beacon", LargeBinary),
    Column("verified_source", Integer),
    Column("abi_json", JSONB),
    Column("first_seen_block", BigInteger),
)
