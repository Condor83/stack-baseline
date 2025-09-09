from ..celery_app import celery_app
from ..clients.alchemy import AlchemyTraceClient
from ..db import session_scope, get_engine
from ..storage import refresh_traces_for_tx, transactions, logs, token_transfers
from sqlalchemy import select
from ..storage import _hex_to_bytes
from ..decoding.abi_resolver import resolve_and_cache_abi
from ..decoding.classifier import classify_tx
from ..clients.prices import PriceService
from ..decoding.decoder import decode_and_store_logs, decode_call_input


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
                transactions.c.method_id,
                transactions.c.function_name,
                transactions.c.input,
            ).where(transactions.c.chain_id == chain_id, transactions.c.hash == txh)
        ).fetchone()
        if not tx_row:
            return {"status": "not_found"}
        tx_id = int(tx_row.id)
        to_addr = tx_row.to_address
        timestamp = int(tx_row.timestamp or 0)
        method_id = None
        if tx_row.method_id is not None:
            try:
                b = tx_row.method_id.tobytes() if isinstance(tx_row.method_id, memoryview) else tx_row.method_id
                method_id = "0x" + b.hex()
            except Exception:
                method_id = None
        function_name = tx_row.function_name

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
        # Build to_address hex
        to_hex = None
        if to_addr is not None:
            to_hex = "0x" + (to_addr.tobytes().hex() if isinstance(to_addr, memoryview) else to_addr.hex())
        c = classify_tx(log_payload, len(transfers_count), chain_id, to_hex, method_id, function_name)

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

        # Decode and store events (best-effort)
        try:
            decoded_count = decode_and_store_logs(chain_id, tx_id)
        except Exception:
            decoded_count = 0

        # Decode call input (best-effort)
        try:
            input_bytes = None
            if tx_row.input is not None:
                input_bytes = tx_row.input.tobytes() if isinstance(tx_row.input, memoryview) else tx_row.input
            call_decoded = decode_call_input(chain_id, to_hex, input_bytes)
        except Exception:
            call_decoded = None

        result = {
            "status": "ok",
            "chain_id": chain_id,
            "tx_id": tx_id,
            "tx_hash": tx_hash,
            "classification": c,
            "cost_usd": usd,
            "decoded_events": decoded_count,
            "decoded_call": call_decoded,
        }
        # Persist classification
        try:
            from sqlalchemy.dialects.postgresql import insert
            from ..storage import classifications_tbl
            conn = get_engine().begin()
            with conn as cc:
                stmt = insert(classifications_tbl).values(
                    tx_id=tx_id,
                    primary_label=c.get("primary_label"),
                    secondary_label=c.get("secondary_label"),
                    protocol=c.get("protocol"),
                    confidence=c.get("confidence"),
                    details_json={"cost_usd": usd, "decoded_call": call_decoded},
                ).on_conflict_do_update(
                    index_elements=[classifications_tbl.c.tx_id],
                    set_={
                        "primary_label": c.get("primary_label"),
                        "secondary_label": c.get("secondary_label"),
                        "protocol": c.get("protocol"),
                        "confidence": c.get("confidence"),
                        "details_json": {"cost_usd": usd, "decoded_call": call_decoded},
                    },
                )
                cc.execute(stmt)
        except Exception:
            pass
        return result


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
