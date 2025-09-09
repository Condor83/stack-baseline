from typing import Dict, Optional

from ..celery_app import celery_app
from ..clients.etherscan_v2 import EtherscanV2Client
from ..db import session_scope, get_engine
from ..storage import (
    upsert_transaction,
    insert_logs_for_tx,
    transactions,
    insert_token_transfers_from_logs,
    update_transaction_receipt_fields,
    internal_txs,
)
from sqlalchemy import select
from ..clients.etherscan_v2 import EtherscanV2Client
from ..storage import _parse_int, _hex_to_bytes


@celery_app.task(name="ingest.fetch_account_txs", queue="ingest")
def fetch_account_txs(chain_id: int, address: str, start_block: int, end_block: int, window: int = 10000) -> int:
    """Fetch and persist transactions for an address using block windows. Returns total txs fetched."""
    client = EtherscanV2Client(chain_id)
    total = 0
    engine = get_engine()
    txhash_to_id: Dict[bytes, int] = {}

    for page in client.iter_txlist_block_windows(address, start_block, end_block, window):
        result = page.get("result", [])
        total += len(result)
        if engine is None:
            continue
        with session_scope() as conn:
            for tx in result:
                tx_id = upsert_transaction(conn, chain_id, tx)
                if tx_id is None:
                    continue
                txh = tx.get("hash")
                if txh:
                    try:
                        bh = bytes.fromhex(txh[2:])
                        txhash_to_id[bh] = tx_id
                    except Exception:
                        pass
                # Fetch receipt and persist logs + token transfers
                if txh:
                    rcpt = client.get_tx_receipt(txh)
                    if rcpt:
                        status = _parse_int(rcpt.get("status"))  # hex 0x1/0x0
                        gas_used = _parse_int(rcpt.get("gasUsed"))
                        egp = _parse_int(rcpt.get("effectiveGasPrice"))
                        update_transaction_receipt_fields(conn, chain_id, bh, status, gas_used, egp)
                        logs_payload = rcpt.get("logs") or []
                        if logs_payload:
                            insert_logs_for_tx(conn, tx_id, logs_payload)
                            insert_token_transfers_from_logs(conn, chain_id, tx_id, logs_payload)

    # Internal txs for the same address and block range
    ingest_internal_transactions(chain_id, address, start_block, end_block, window, txhash_to_id)
    return total


def ingest_internal_transactions(
    chain_id: int, address: str, start_block: int, end_block: int, window: int, txhash_to_id: Dict[bytes, int]
) -> int:
    engine = get_engine()
    if engine is None:
        return 0
    client = EtherscanV2Client(chain_id)
    total = 0
    cur = start_block
    while cur <= end_block:
        w_end = min(end_block, cur + window - 1)
        resp = client.get_internal_txs(address=address, startblock=cur, endblock=w_end)
        items = resp.get("result", [])
        if not items:
            cur = w_end + 1
            continue
        with session_scope() as conn:
            for it in items:
                txh = it.get("hash")
                if not txh:
                    continue
                try:
                    bh = bytes.fromhex(txh[2:])
                except Exception:
                    continue
                # find tx_id
                tx_id = txhash_to_id.get(bh)
                if tx_id is None:
                    row = conn.execute(select(transactions.c.id).where(transactions.c.chain_id == chain_id, transactions.c.hash == bh)).fetchone()
                    if row:
                        tx_id = int(row[0])
                values = {
                    "tx_id": tx_id,
                    "trace_id": it.get("traceId"),
                    "type": it.get("type"),
                    "from_address": _hex_to_bytes(it.get("from")),
                    "to_address": _hex_to_bytes(it.get("to")),
                    "value": _parse_int(it.get("value")),
                    "contract_address": _hex_to_bytes(it.get("contractAddress")),
                    "is_error": _parse_int(it.get("isError")),
                    "error_code": it.get("errCode"),
                    "gas": _parse_int(it.get("gas")),
                    "gas_used": _parse_int(it.get("gasUsed")),
                }
                conn.execute(internal_txs.insert().values(**values))
                total += 1
        cur = w_end + 1
    return total
