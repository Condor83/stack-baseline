from ..celery_app import celery_app
from ..clients.alchemy import AlchemyTraceClient
from ..db import session_scope, get_engine
from ..storage import refresh_traces_for_tx, transactions, logs, token_transfers
from sqlalchemy import select
from ..storage import _hex_to_bytes
from ..decoding.abi_resolver import resolve_and_cache_abi
from ..decoding.classifier import classify_tx
from ..clients.prices import PriceService


@celery_app.task(name="decode.decode_tx", queue="decode")
def decode_tx(chain_id: int, tx_hash: str) -> dict:
    engine = get_engine()
    if engine is None:
        return {"status": "skipped", "reason": "no_db"}
    txh = _hex_to_bytes(tx_hash)
    if txh is None:
        return {"status": "error", "error": "invalid_tx_hash"}
    with session_scope() as conn:
        tx_row = conn.execute(
            select(
                transactions.c.id,
                transactions.c.to_address,
                transactions.c.timestamp,
                transactions.c.gas_used,
                transactions.c.effective_gas_price,
            ).where(transactions.c.chain_id == chain_id, transactions.c.hash == txh)
        ).fetchone()
        if not tx_row:
            return {"status": "not_found"}
        tx_id = int(tx_row.id)
        to_addr = tx_row.to_address
        timestamp = int(tx_row.timestamp or 0)

        # Collect logs for classification
        log_rows = conn.execute(
            select(logs.c.topics, logs.c.address, logs.c.log_index).where(logs.c.tx_id == tx_id)
        ).fetchall()
        log_payload = []
        for r in log_rows:
            topics_str = None
            if r.topics is not None:
                tstr = r.topics.tobytes().decode() if isinstance(r.topics, memoryview) else r.topics.decode()
                topics_str = tstr.split("|")
            log_payload.append({
                "topics": topics_str,
                "address": "0x" + (r.address.tobytes().hex() if isinstance(r.address, memoryview) else (r.address.hex() if isinstance(r.address, (bytes, bytearray)) else "")),
                "logIndex": r.log_index,
            })
        transfers_count = conn.execute(
            select(token_transfers.c.id).where(token_transfers.c.tx_id == tx_id)
        ).fetchall()
        c = classify_tx(log_payload, len(transfers_count))

        # Cost (USD)
        gas_used = int(tx_row.gas_used or 0)
        egp = int(tx_row.effective_gas_price or 0)
        usd = None
        if gas_used and egp and timestamp:
            svc = PriceService()
            # native address sentinel 'native'
            pres = svc.get_price_usd(chain_id, "native", timestamp)
            if pres:
                usd = (gas_used * egp / 1e18) * pres[0]

        return {
            "status": "ok",
            "chain_id": chain_id,
            "tx_id": tx_id,
            "tx_hash": tx_hash,
            "classification": c,
            "cost_usd": usd,
        }


@celery_app.task(name="decode.fetch_traces", queue="decode")
def fetch_traces(chain_id: int, tx_hash: str) -> dict:
    engine = get_engine()
    if engine is None:
        return {"status": "skipped", "reason": "no_db"}
    try:
        txh_bytes = _hex_to_bytes(tx_hash)
        if txh_bytes is None:
            return {"status": "error", "error": "invalid_tx_hash"}
    except Exception:
        return {"status": "error", "error": "invalid_tx_hash"}

    with session_scope() as conn:
        row = conn.execute(
            select(transactions.c.id).where(transactions.c.chain_id == chain_id, transactions.c.hash == txh_bytes)
        ).fetchone()
        if not row:
            return {"status": "error", "error": "tx_not_found"}
        tx_id = int(row[0])

    # Call Alchemy trace if budget allows
    try:
        rc_client = None
        try:
            import redis as _redis  # type: ignore
            from ..config import get_settings
            settings = get_settings()
            rc_client = _redis.from_url(settings.redis_url) if settings.redis_url else None
        except Exception:
            rc_client = None
        client = AlchemyTraceClient(chain_id, redis_client=rc_client)
        result = client.trace_transaction(tx_hash)
        if result is None:
            return {"status": "skipped", "reason": "no_budget_or_no_result"}
        # Persist traces
        with session_scope() as conn:
            n = refresh_traces_for_tx(conn, tx_id, chain_id, txh_bytes, result)
        return {"status": "ok", "traces": n}
    except Exception as e:
        return {"status": "error", "error": str(e)}
