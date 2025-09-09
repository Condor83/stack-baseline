from typing import Optional, Dict

import httpx

from ..config import get_settings
from ..rate_limiter import build_limiter, rps_to_window


class AlchemyTraceClient:
    def __init__(self, chain_id: int):
        self.settings = get_settings()
        self.chain_id = chain_id
        self.http = httpx.Client(timeout=60)
        self.limiter = build_limiter(self.settings.redis_url)
        # Map chain_id to Alchemy URL prefix; user should supply the correct URL via env in future.
        # For now, we assume https://{network}.g.alchemy.com/v2/{ALCHEMY_API_KEY}
        self.base = None

    def _rpc(self, method: str, params: list) -> Optional[Dict]:
        if not self.settings.alchemy_api_key:
            return None
        # Budget guard could be implemented using Redis counters similar to prices
        url = f"https://eth-mainnet.g.alchemy.com/v2/{self.settings.alchemy_api_key}"
        # TODO: map chain_id to correct network host (e.g., arbitrum-mainnet, opt-mainnet)
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

