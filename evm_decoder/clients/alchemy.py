from typing import Optional, Dict, Tuple, List

import httpx

from ..config import get_settings
from ..rate_limiter import build_limiter, rps_to_window
try:
    import redis as _redis
except Exception:  # pragma: no cover
    _redis = None  # type: ignore


def _network_host(chain_id: int) -> Optional[str]:
    return {
        1: "eth-mainnet",
        42161: "arb-mainnet",
        10: "opt-mainnet",
        8453: "base-mainnet",
        137: "polygon-mainnet",
    }.get(chain_id)


class AlchemyTraceClient:
    def __init__(self, chain_id: int, redis_client=None):
        self.settings = get_settings()
        self.chain_id = chain_id
        self.http = httpx.Client(timeout=60)
        self.limiter = build_limiter(self.settings.redis_url)
        self.redis = redis_client

    def _budget_ok(self) -> bool:
        budget = int(self.settings.traces_daily_budget_alchemy or 0)
        if budget <= 0 or self.redis is None:
            return False
        key = f"trace:alchemy:used:{self.chain_id}:{__import__('time').strftime('%Y%m%d')}"
        used = int(self.redis.incr(key))
        self.redis.expire(key, 86400)
        return used <= budget

    def _rpc(self, method: str, params: list) -> Optional[Dict]:
        if not self.settings.alchemy_api_key:
            return None
        host = _network_host(self.chain_id)
        if not host:
            return None
        if not self._budget_ok():
            return None
        url = f"https://{host}.g.alchemy.com/v2/{self.settings.alchemy_api_key}"
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        win = rps_to_window(1.0)  # conservative default 1 rps
        win.key = "alchemy"
        with self.limiter.limit(win.key, win.limit, win.window_seconds):
            resp = self.http.post(url, json=payload)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("result")

    def trace_transaction(self, tx_hash: str) -> Optional[Dict]:
        return self._rpc("trace_transaction", [tx_hash])

    def debug_trace_transaction(self, tx_hash: str, tracer: Optional[Dict] = None) -> Optional[Dict]:
        params = [tx_hash]
        if tracer:
            params.append(tracer)
        return self._rpc("debug_traceTransaction", params)
