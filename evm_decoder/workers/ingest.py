from typing import Dict, Optional

from ..celery_app import celery_app
from ..clients.etherscan_v2 import EtherscanV2Client
from ..db import session_scope, get_engine
from ..storage import upsert_transaction, insert_logs_for_tx, transactions
from sqlalchemy import select


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
                if tx_id is not None and tx.get("hash"):
                    try:
                        txhash_to_id[bytes.fromhex(tx["hash"][2:])] = tx_id
                    except Exception:
                        pass
    # Fetch logs for the same range and address, then persist mapped to tx_id
    persist_logs_for_range(chain_id, address, start_block, end_block, window, txhash_to_id)
    return total


def persist_logs_for_range(
    chain_id: int, address: str, start_block: int, end_block: int, window: int, txhash_to_id: Dict[bytes, int]
) -> int:
    engine = get_engine()
    if engine is None:
        return 0
    client = EtherscanV2Client(chain_id)
    count = 0
    cur = start_block
    while cur <= end_block:
        w_end = min(end_block, cur + window - 1)
        data = client.get_logs(address=address, from_block=cur, to_block=w_end)
        logs_res = data.get("result", [])
        if not logs_res:
            cur = w_end + 1
            continue
        # group by tx hash
        grouped: Dict[bytes, list] = {}
        for l in logs_res:
            txh = l.get("transactionHash")
            if not txh:
                continue
            try:
                bh = bytes.fromhex(txh[2:])
            except Exception:
                continue
            grouped.setdefault(bh, []).append(l)

        with session_scope() as conn:
            for th, items in grouped.items():
                tx_id = txhash_to_id.get(th)
                if tx_id is None:
                    # Try lookup
                    row = conn.execute(select(transactions.c.id).where(transactions.c.chain_id == chain_id, transactions.c.hash == th)).fetchone()
                    if row:
                        tx_id = int(row[0])
                if tx_id is None:
                    continue
                count += insert_logs_for_tx(conn, tx_id, items)
        cur = w_end + 1
    return count
