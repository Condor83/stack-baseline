import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Body, HTTPException, Query

from ..config import get_settings
from ..workers.prices import get_price as price_task
from ..clients.prices import PriceService
from ..utils.chains import is_native_address
from ..clients.etherscan_v2 import EtherscanV2Client
from ..workers.ingest import fetch_account_txs
from ..workers.decode import fetch_traces
from ..celery_app import celery_app
from celery.result import AsyncResult
from ..db import get_engine
from sqlalchemy import select, and_, or_, func
from ..storage import transactions, logs, token_transfers
from decimal import Decimal


def _to_hex(value):
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()
    if isinstance(value, str):
        return value
    return None


def _to_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _to_str_number(v):
    if isinstance(v, Decimal):
        return str(v)
    return v


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
    engine = get_engine()
    if engine is None:
        return {"status": "not_implemented", "tx_hash": tx_hash}
    try:
        txh = bytes.fromhex(tx_hash.lower().removeprefix("0x"))
    except Exception:
        return {"status": "error", "error": "invalid_tx_hash"}
    with engine.begin() as conn:
        row = conn.execute(
            select(
                transactions.c.chain_id,
                transactions.c.hash,
                transactions.c.block_number,
                transactions.c.transaction_index,
                transactions.c.timestamp,
                transactions.c.from_address,
                transactions.c.to_address,
                transactions.c.value,
                transactions.c.status,
                transactions.c.gas_used,
                transactions.c.effective_gas_price,
            ).where(transactions.c.hash == txh)
        ).fetchone()
    if not row:
        return {"status": "not_found", "tx_hash": tx_hash}
    # Attach classification if present
    classification = None
    try:
        from ..storage import classifications_tbl
        with get_engine().begin() as conn:
            c_row = conn.execute(
                select(
                    classifications_tbl.c.primary_label,
                    classifications_tbl.c.secondary_label,
                    classifications_tbl.c.protocol,
                    classifications_tbl.c.confidence,
                    classifications_tbl.c.details_json,
                ).where(classifications_tbl.c.tx_id == select(transactions.c.id).where(transactions.c.hash == txh).scalar_subquery())
            ).fetchone()
            if c_row:
                classification = {
                    "primary_label": c_row.primary_label,
                    "secondary_label": c_row.secondary_label,
                    "protocol": c_row.protocol,
                    "confidence": float(c_row.confidence) if c_row.confidence is not None else None,
                    "details": c_row.details_json,
                }
    except Exception:
        classification = None
    resp = {
        "chain_id": int(row.chain_id),
        "tx_hash": _to_hex(row.hash),
        "block_number": _to_int(row.block_number),
        "transaction_index": _to_int(row.transaction_index),
        "timestamp": _to_int(row.timestamp),
        "from": _to_hex(row.from_address),
        "to": _to_hex(row.to_address),
        "value": _to_str_number(row.value),
        "status": _to_int(row.status),
        "gas_used": _to_int(row.gas_used),
        "effective_gas_price": _to_int(row.effective_gas_price),
    }
    if classification:
        resp["classification"] = classification
    return resp


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


def _parse_time_to_epoch(value) -> int:
    import time as _time
    from datetime import datetime, timezone
    if value is None:
        return int(_time.time())
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        try:
            dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid time format; use epoch seconds or ISO8601 (e.g., 2024-01-01T00:00:00Z)")


@app.post("/api/v1/ingest/address_by_date")
def ingest_address_by_date(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    chain_id = int(payload.get("chain_id", 0))
    address = str(payload.get("address", ""))
    start_raw = payload.get("start")
    end_raw = payload.get("end")
    window = int(payload.get("window", 10000))
    if not chain_id or not address:
        raise HTTPException(status_code=400, detail="chain_id and address are required")
    start_ts = _parse_time_to_epoch(start_raw) if start_raw is not None else int(time.time()) - 24 * 3600
    end_ts = _parse_time_to_epoch(end_raw) if end_raw is not None else int(time.time())
    if end_ts < start_ts:
        raise HTTPException(status_code=400, detail="end must be >= start")
    client = EtherscanV2Client(chain_id)
    start_block = client.get_block_number_by_time(start_ts, closest="after") or 0
    end_block = client.get_block_number_by_time(end_ts, closest="before") or start_block
    if end_block < start_block:
        end_block = start_block
    task = fetch_account_txs.delay(chain_id, address, start_block, end_block, window)
    return {
        "task_id": task.id,
        "status": "queued",
        "start_block": start_block,
        "end_block": end_block,
        "start_ts": start_ts,
        "end_ts": end_ts,
    }


@app.get("/api/v1/tasks/{task_id}")
def task_status(task_id: str) -> Dict[str, Any]:
    r = AsyncResult(task_id, app=celery_app)
    payload: Dict[str, Any] = {"task_id": task_id, "state": r.state}
    # Include meta/progress if available
    info = getattr(r, "info", None)
    if isinstance(info, dict):
        payload["meta"] = info
    if r.successful():
        try:
            payload["result"] = r.get(timeout=0)
        except Exception:
            payload["result"] = None
    elif r.failed():
        payload["error"] = str(r.result)
    return payload


@app.get("/api/v1/address/{chain_id}/{address}/summary")
def address_summary(
    chain_id: int,
    address: str,
    from_block: int | None = Query(None),
    to_block: int | None = Query(None),
):
    engine = get_engine()
    if engine is None:
        raise HTTPException(status_code=500, detail="Database not configured. Set DATABASE_URL or SUPABASE_DB_URL.")
    try:
        addr_bytes = bytes.fromhex(address.lower().removeprefix("0x"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid address hex")

    with engine.begin() as conn:
        cond = [transactions.c.chain_id == chain_id]
        if from_block is not None:
            cond.append(transactions.c.block_number >= from_block)
        if to_block is not None:
            cond.append(transactions.c.block_number <= to_block)

        count_chain = conn.execute(
            select(func.count()).select_from(transactions).where(*cond)
        ).scalar_one()

        from_count = conn.execute(
            select(func.count()).select_from(transactions).where(*(cond + [transactions.c.from_address == addr_bytes]))
        ).scalar_one()
        to_count = conn.execute(
            select(func.count()).select_from(transactions).where(*(cond + [transactions.c.to_address == addr_bytes]))
        ).scalar_one()
        addr_tx_count = int(from_count) + int(to_count)

        logs_cond = cond + [logs.c.address == addr_bytes]
        logs_count = conn.execute(
            select(func.count()).select_from(logs.join(transactions, logs.c.tx_id == transactions.c.id)).where(*logs_cond)
        ).scalar_one()

        min_block = conn.execute(
            select(func.min(transactions.c.block_number)).where(
                transactions.c.chain_id == chain_id,
                or_(transactions.c.from_address == addr_bytes, transactions.c.to_address == addr_bytes),
            )
        ).scalar_one()
        max_block = conn.execute(
            select(func.max(transactions.c.block_number)).where(
                transactions.c.chain_id == chain_id,
                or_(transactions.c.from_address == addr_bytes, transactions.c.to_address == addr_bytes),
            )
        ).scalar_one()

    return {
        "chain_id": chain_id,
        "address": address,
        "tx_count_chain_window": int(count_chain),
        "tx_count_for_address": int(addr_tx_count),
        "logs_count_for_address": int(logs_count or 0),
        "address_block_range": {
            "min": _to_int(min_block),
            "max": _to_int(max_block),
        },
    }


@app.get("/api/v1/address/{chain_id}/{address}/transactions")
def address_transactions(
    chain_id: int,
    address: str,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    from_block: int | None = Query(None),
    to_block: int | None = Query(None),
):
    engine = get_engine()
    if engine is None:
        raise HTTPException(status_code=500, detail="Database not configured. Set DATABASE_URL or SUPABASE_DB_URL.")
    try:
        addr_bytes = bytes.fromhex(address.lower().removeprefix("0x"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid address hex")
    with engine.begin() as conn:
        cond = [transactions.c.chain_id == chain_id,
                or_(transactions.c.from_address == addr_bytes, transactions.c.to_address == addr_bytes)]
        if from_block is not None:
            cond.append(transactions.c.block_number >= from_block)
        if to_block is not None:
            cond.append(transactions.c.block_number <= to_block)
        rows = conn.execute(
            select(
                transactions.c.hash,
                transactions.c.block_number,
                transactions.c.transaction_index,
                transactions.c.timestamp,
                transactions.c.from_address,
                transactions.c.to_address,
                transactions.c.value,
                transactions.c.status,
            )
            .where(*cond)
            .order_by(transactions.c.block_number.desc(), transactions.c.transaction_index.desc())
            .limit(limit)
            .offset(offset)
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "tx_hash": _to_hex(r.hash),
            "block_number": _to_int(r.block_number),
            "transaction_index": _to_int(r.transaction_index),
            "timestamp": _to_int(r.timestamp),
            "from": _to_hex(r.from_address),
            "to": _to_hex(r.to_address),
            "value": _to_str_number(r.value),
            "status": _to_int(r.status),
        })
    return {"items": out, "limit": limit, "offset": offset}


@app.get("/api/v1/address/{chain_id}/{address}/logs")
def address_logs(
    chain_id: int,
    address: str,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    from_block: int | None = Query(None),
    to_block: int | None = Query(None),
):
    engine = get_engine()
    if engine is None:
        raise HTTPException(status_code=500, detail="Database not configured. Set DATABASE_URL or SUPABASE_DB_URL.")
    try:
        addr_bytes = bytes.fromhex(address.lower().removeprefix("0x"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid address hex")

    with engine.begin() as conn:
        cond = [transactions.c.chain_id == chain_id, logs.c.address == addr_bytes]
        if from_block is not None:
            cond.append(transactions.c.block_number >= from_block)
        if to_block is not None:
            cond.append(transactions.c.block_number <= to_block)
        rows = conn.execute(
            select(
                logs.c.log_index,
                logs.c.address,
                logs.c.topics,
                transactions.c.hash,
                transactions.c.block_number,
            )
            .select_from(logs.join(transactions, logs.c.tx_id == transactions.c.id))
            .where(*cond)
            .order_by(transactions.c.block_number.desc(), logs.c.log_index.desc())
            .limit(limit)
            .offset(offset)
        ).fetchall()
    items = []
    for r in rows:
        topic0 = None
        if r.topics is not None:
            try:
                tstr = r.topics.tobytes().decode() if isinstance(r.topics, memoryview) else r.topics.decode()
                topic0 = tstr.split("|")[0]
            except Exception:
                topic0 = None
        items.append({
            "tx_hash": _to_hex(r.hash),
            "block_number": _to_int(r.block_number),
            "log_index": _to_int(r.log_index),
            "address": _to_hex(r.address),
            "topic0": topic0,
        })
    return {"items": items, "limit": limit, "offset": offset}


@app.get("/api/v1/address/{chain_id}/{address}/token_transfers")
def address_token_transfers(
    chain_id: int,
    address: str,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    from_block: int | None = Query(None),
    to_block: int | None = Query(None),
):
    engine = get_engine()
    if engine is None:
        raise HTTPException(status_code=500, detail="Database not configured. Set DATABASE_URL or SUPABASE_DB_URL.")
    try:
        addr_bytes = bytes.fromhex(address.lower().removeprefix("0x"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid address hex")
    with engine.begin() as conn:
        # Transfers where address is token contract OR participant
        cond_core = [transactions.c.chain_id == chain_id]
        if from_block is not None:
            cond_core.append(transactions.c.block_number >= from_block)
        if to_block is not None:
            cond_core.append(transactions.c.block_number <= to_block)
        cond = cond_core + [
            or_(token_transfers.c.token_address == addr_bytes,
                token_transfers.c.from_address == addr_bytes,
                token_transfers.c.to_address == addr_bytes)
        ]
        rows = conn.execute(
            select(
                transactions.c.hash,
                transactions.c.block_number,
                token_transfers.c.standard,
                token_transfers.c.log_index,
                token_transfers.c.token_address,
                token_transfers.c.from_address,
                token_transfers.c.to_address,
                token_transfers.c.value,
                token_transfers.c.token_id,
            )
            .select_from(token_transfers.join(transactions, token_transfers.c.tx_id == transactions.c.id))
            .where(*cond)
            .order_by(transactions.c.block_number.desc(), token_transfers.c.log_index.desc().nulls_last())
            .limit(limit)
            .offset(offset)
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "tx_hash": _to_hex(r.hash),
            "block_number": _to_int(r.block_number),
            "standard": r.standard,
            "log_index": _to_int(r.log_index),
            "token": _to_hex(r.token_address),
            "from": _to_hex(r.from_address),
            "to": _to_hex(r.to_address),
            "value": _to_str_number(r.value),
            "token_id": _to_int(r.token_id),
        })
    return {"items": out, "limit": limit, "offset": offset}


@app.post("/api/v1/traces/{chain_id}/{tx_hash}")
def request_traces(chain_id: int, tx_hash: str) -> Dict[str, Any]:
    task = fetch_traces.delay(chain_id, tx_hash)
    return {"task_id": task.id, "status": "queued"}


@app.post("/api/v1/decode/{chain_id}/{tx_hash}")
def request_decode(chain_id: int, tx_hash: str) -> Dict[str, Any]:
    from ..workers.decode import decode_tx as decode_task
    task = decode_task.delay(chain_id, tx_hash)
    return {"task_id": task.id, "status": "queued"}
