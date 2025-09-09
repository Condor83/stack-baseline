from typing import Optional

from ..celery_app import celery_app
from ..clients.etherscan_v2 import EtherscanV2Client


@celery_app.task(name="ingest.fetch_account_txs", queue="ingest")
def fetch_account_txs(chain_id: int, address: str, start_block: int, end_block: int, window: int = 10000) -> int:
    """Fetch transactions for an address using block windows. Returns total txs fetched.

    Note: This is a scaffold. Persisting to DB and deduplication are TODOs.
    """
    client = EtherscanV2Client(chain_id)
    total = 0
    for page in client.iter_txlist_block_windows(address, start_block, end_block, window):
        result = page.get("result", [])
        total += len(result)
        # TODO: persist transactions
    return total

