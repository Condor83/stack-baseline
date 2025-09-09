import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Body, HTTPException

from ..config import get_settings
from ..workers.prices import get_price as price_task
from ..clients.prices import PriceService
from ..utils.chains import is_native_address
from ..workers.ingest import fetch_account_txs


settings = get_settings()
app = FastAPI(title="EVM Decoder API", version="0.1.0")


@app.get("/health")
def health() -> Dict[str, Any]:
    # Lightweight health; we don't hard-require Redis here
    return {
        "status": "ok",
        "env": settings.env,
        "redis": bool(settings.redis_url),
        "supabase_url": bool(settings.supabase_url),
    }


@app.get("/api/v1/tx/{tx_hash}")
def get_tx(tx_hash: str) -> Dict[str, Any]:
    return {"status": "not_implemented", "tx_hash": tx_hash}


@app.get("/api/v1/wallets/{address}/portfolio")
def get_wallet_portfolio(address: str) -> Dict[str, Any]:
    return {"status": "not_implemented", "address": address}


@app.get("/api/v1/price/{chain_id}/{contract}")
def get_price(chain_id: int, contract: str, ts: Optional[int] = None) -> Dict[str, Any]:
    """Return minute-bucketed USD price for a token or the native asset.

    contract may be a hex address or 'native'/zero/eeee sentinel.
    ts is a unix timestamp (seconds). Defaults to now.
    """
    timestamp = ts or int(time.time())
    svc = PriceService()
    res = svc.get_price_usd(chain_id, contract, timestamp)
    return {
        "chain_id": chain_id,
        "contract": contract,
        "timestamp": timestamp,
        "price_usd": res[0] if res else None,
        "source": res[1] if res else None,
    }


@app.post("/api/v1/ingest/address")
def ingest_address(
    payload: Dict[str, Any] = Body(
        ..., example={"chain_id": 1, "address": "0xabc...", "start_block": 0, "end_block": 99999999, "window": 10000}
    )
) -> Dict[str, Any]:
    chain_id = int(payload.get("chain_id", 0))
    address = str(payload.get("address", ""))
    start_block = int(payload.get("start_block", 0))
    end_block = int(payload.get("end_block", 0))
    window = int(payload.get("window", 10000))
    if not chain_id or not address or end_block < start_block:
        raise HTTPException(status_code=400, detail="Invalid payload")
    # Enqueue task
    task = fetch_account_txs.delay(chain_id, address, start_block, end_block, window)
    return {"task_id": task.id, "status": "queued"}
