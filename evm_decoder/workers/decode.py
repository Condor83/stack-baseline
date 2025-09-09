from ..celery_app import celery_app


@celery_app.task(name="decode.decode_tx", queue="decode")
def decode_tx(chain_id: int, tx_hash: str) -> dict:
    # TODO: implement decoding pipeline (ABI fetch, proxy resolution, traces, event parsing)
    return {"status": "not_implemented", "chain_id": chain_id, "tx_hash": tx_hash}

