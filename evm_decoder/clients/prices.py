import math
import time
from typing import Optional, Tuple

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from ..config import get_settings
from ..rate_limiter import build_limiter, rps_to_window


class PriceError(Exception):
    pass


def _minute_bucket(ts: int) -> int:
    return ts - (ts % 60)


class PriceService:
    """Price oracle with provider order: Cache → DB → CoinGecko → DeFiLlama → Alchemy.

    Caches minute-bucketed USD prices for (chain_id, contract).
    """

    def __init__(self, redis_client=None):
        self.settings = get_settings()
        self.http = httpx.Client(timeout=30)
        self.limiter = build_limiter(self.settings.redis_url)
        self.redis = redis_client

    def _cache_key(self, chain_id: int, contract: str, minute: int) -> str:
        return f"price:{chain_id}:{contract.lower()}:{minute}"

    def get_price_usd(
        self, chain_id: int, contract: str, timestamp: int
    ) -> Optional[Tuple[float, str]]:
        minute = _minute_bucket(timestamp)
        # 1) Redis cache
        if self.redis is not None:
            raw = self.redis.get(self._cache_key(chain_id, contract, minute))
            if raw:
                try:
                    price, source = raw.decode().split(":", 1)
                    return float(price), source
                except Exception:
                    pass

        # 2) DB cache (TODO): read from prices table if present
        # price = self._db_lookup(chain_id, contract, minute)  # not implemented yet
        # if price is not None:
        #     return price, "db"

        # 3) Providers
        price = self._from_coingecko(chain_id, contract, minute)
        if price is None:
            price = self._from_llama(chain_id, contract, minute)
        if price is None:
            price = self._from_alchemy(chain_id, contract, minute)

        if price is None:
            return None

        val, source = price
        if self.redis is not None:
            self.redis.setex(self._cache_key(chain_id, contract, minute), 3600, f"{val}:{source}")
        return price

    # --- Providers ---
    @retry(
        retry=retry_if_exception_type(PriceError),
        wait=wait_exponential_jitter(initial=0.5, max=5),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _from_coingecko(self, chain_id: int, contract: str, minute: int) -> Optional[Tuple[float, str]]:
        # NOTE: Implement the correct mapping from chain_id→coingecko platform and
        # use contract-address routes with /market_chart/range. For now, stubbed.
        if float(self.settings.coingecko_rps) <= 0:
            return None
        win = rps_to_window(float(self.settings.coingecko_rps))
        win.key = "coingecko"
        with self.limiter.limit(win.key, win.limit, win.window_seconds):
            # TODO: add real request/response parsing
            return None

    @retry(
        retry=retry_if_exception_type(PriceError),
        wait=wait_exponential_jitter(initial=0.5, max=5),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _from_llama(self, chain_id: int, contract: str, minute: int) -> Optional[Tuple[float, str]]:
        if float(self.settings.llama_rps) <= 0:
            return None
        win = rps_to_window(float(self.settings.llama_rps))
        win.key = "defillama"
        with self.limiter.limit(win.key, win.limit, win.window_seconds):
            # TODO: add real request/response parsing
            return None

    def _from_alchemy(self, chain_id: int, contract: str, minute: int) -> Optional[Tuple[float, str]]:
        # Guard with daily budget; increment a Redis counter
        budget = self.settings.price_daily_budget_alchemy
        if budget <= 0:
            return None
        counter_key = f"price:alchemy:used:{time.strftime('%Y%m%d')}"
        used = 0
        if self.redis is not None:
            used = int(self.redis.incr(counter_key))
            self.redis.expire(counter_key, 86400)
        if used > budget:
            return None
        # TODO: implement real Alchemy-backed price fallback (if available/desired)
        return None
