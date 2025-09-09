from ..celery_app import celery_app
from ..clients.alchemy import AlchemyTraceClient
from ..db import session_scope, get_engine
from ..storage import refresh_traces_for_tx, transactions
from sqlalchemy import select
from ..storage import _hex_to_bytes


@celery_app.task(name="decode.decode_tx", queue="decode")
def decode_tx(chain_id: int, tx_hash: str) -> dict:
    # TODO: implement decoding pipeline (ABI fetch, proxy resolution, traces, event parsing)
    return {"status": "not_implemented", "chain_id": chain_id, "tx_hash": tx_hash}


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
