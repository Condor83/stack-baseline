from ..celery_app import celery_app


@celery_app.task(name="analytics.compute_costs", queue="analytics")
def compute_costs(chain_id: int, tx_hash: str) -> dict:
    # TODO: implement cost adapters (EIP-1559, OP/ARB components) and P&L aggregation
    return {"status": "not_implemented", "chain_id": chain_id, "tx_hash": tx_hash}

