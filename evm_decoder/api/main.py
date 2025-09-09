from typing import Any, Dict

from fastapi import FastAPI

from ..config import get_settings


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

