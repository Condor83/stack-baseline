import math
import time
from typing import Optional, Tuple, List

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from ..config import get_settings
from ..rate_limiter import build_limiter, rps_to_window
from ..db import get_engine
from sqlalchemy import select
from ..storage import prices_tbl
from ..utils.chains import (
    coingecko_platform,
    coingecko_native_coin_id,
    llama_chain_slug,
    is_native_address,
)


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
        self.engine = get_engine()

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

        # 2) DB cache: read from prices table
        db_hit = self._db_lookup(chain_id, contract, minute)
        if db_hit is not None:
            return db_hit, "db"

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
        # upsert DB
        self._db_upsert(chain_id, contract, minute, val)
        return price

    # --- Providers ---
    def _from_coingecko(self, chain_id: int, contract: str, minute: int) -> Optional[Tuple[float, str]]:
        # Historical minute price via /market_chart/range
        if float(self.settings.coingecko_rps) <= 0:
            return None
        win = rps_to_window(float(self.settings.coingecko_rps))
        win.key = "coingecko"
        with self.limiter.limit(win.key, win.limit, win.window_seconds):
            try:
                from_ts = minute - 60
                to_ts = minute + 60
                headers = {}
                params_auth = {}
                tier = (self.settings.coingecko_api_tier or "free").lower()
                if tier == "pro" and self.settings.coingecko_api_key:
                    base = "https://pro-api.coingecko.com/api/v3"
                    headers["x-cg-pro-api-key"] = self.settings.coingecko_api_key
                else:
                    # default to public API host; if key present, pass via demo query param
                    base = "https://api.coingecko.com/api/v3"
                    if self.settings.coingecko_api_key:
                        params_auth["x_cg_demo_api_key"] = self.settings.coingecko_api_key

                if is_native_address(contract):
                    coin_id = coingecko_native_coin_id(chain_id)
                    if not coin_id:
                        return None
                    url = f"{base}/coins/{coin_id}/market_chart/range"
                    params = {"vs_currency": "usd", "from": str(from_ts), "to": str(to_ts), **params_auth}
                else:
                    platform = coingecko_platform(chain_id)
                    if not platform:
                        return None
                    url = f"{base}/coins/{platform}/contract/{contract}/market_chart/range"
                    params = {"vs_currency": "usd", "from": str(from_ts), "to": str(to_ts), **params_auth}

                resp = self.http.get(url, params=params, headers=headers)
                if resp.status_code == 429:
                    return None
                if resp.status_code >= 500:
                    return None
                if resp.status_code != 200:
                    # 4xx most likely invalid request/unauthorized/missing mapping; treat as miss
                    return None
                data = resp.json()
                prices: List[List[float]] = data.get("prices") or []
                if not prices:
                    return None
                # prices: [[ms, price], ...]; pick latest at or before minute+60s
                cutoff_ms = (minute + 60) * 1000
                candidates = [p for p in prices if int(p[0]) <= cutoff_ms]
                if not candidates:
                    return None
                val = float(candidates[-1][1])
                return val, "coingecko"
            except Exception as e:
                return None

    def _from_llama(self, chain_id: int, contract: str, minute: int) -> Optional[Tuple[float, str]]:
        if float(self.settings.llama_rps) <= 0:
            return None
        win = rps_to_window(float(self.settings.llama_rps))
        win.key = "defillama"
        with self.limiter.limit(win.key, win.limit, win.window_seconds):
            try:
                if is_native_address(contract):
                    # Use coingecko:<coin_id> key for native assets
                    coin_id = coingecko_native_coin_id(chain_id)
                    if not coin_id:
                        return None
                    coin_key = f"coingecko:{coin_id}"
                else:
                    slug = llama_chain_slug(chain_id)
                    if not slug:
                        return None
                    coin_key = f"{slug}:{contract.lower()}"

                url = f"https://coins.llama.fi/prices/historical/{minute}/{coin_key}"
                resp = self.http.get(url)
                if resp.status_code == 429:
                    return None
                if resp.status_code >= 500:
                    return None
                if resp.status_code != 200:
                    return None
                data = resp.json()
                coins = data.get("coins") or {}
                rec = coins.get(coin_key)
                if not rec:
                    return None
                price = rec.get("price")
                if price is None:
                    return None
                return float(price), "defillama"
            except Exception as e:
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

    # --- DB helpers ---
    def _db_lookup(self, chain_id: int, contract: str, minute: int) -> Optional[float]:
        if self.engine is None:
            return None
        addr = contract.lower().encode()
        minute_key = str(minute)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(prices_tbl.c.price_usd).where(
                    prices_tbl.c.chain_id == chain_id,
                    prices_tbl.c.contract == addr,
                    prices_tbl.c.minute == minute_key,
                )
            ).fetchone()
            if row and row[0] is not None:
                try:
                    return float(row[0])
                except Exception:
                    return None
        return None

    def _db_upsert(self, chain_id: int, contract: str, minute: int, price: float) -> None:
        if self.engine is None:
            return
        from sqlalchemy.dialects.postgresql import insert
        addr = contract.lower().encode()
        minute_key = str(minute)
        with self.engine.begin() as conn:
            stmt = insert(prices_tbl).values(
                chain_id=chain_id,
                contract=addr,
                minute=minute_key,
                price_usd=price,
            ).on_conflict_do_update(
                index_elements=[prices_tbl.c.chain_id, prices_tbl.c.contract, prices_tbl.c.minute],
                set_={"price_usd": price},
            )
            conn.execute(stmt)
