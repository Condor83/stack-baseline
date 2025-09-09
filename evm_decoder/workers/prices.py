from typing import Optional

try:
    import redis
except Exception:  # pragma: no cover
    redis = None  # type: ignore

from ..celery_app import celery_app
from ..clients.prices import PriceService
from ..config import get_settings


settings = get_settings()


def _redis_client():
    if settings.redis_url and redis is not None:
        return redis.from_url(settings.redis_url)
    return None


@celery_app.task(name="prices.get_price", queue="prices")
def get_price(chain_id: int, contract: str, timestamp: int) -> Optional[float]:
    svc = PriceService(redis_client=_redis_client())
    res = svc.get_price_usd(chain_id, contract, timestamp)
    return res[0] if res else None

