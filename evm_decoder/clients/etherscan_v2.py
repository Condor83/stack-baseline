import time
from typing import Dict, Generator, Iterable, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from ..config import get_settings
from ..rate_limiter import build_limiter, rps_to_window


class EtherscanError(Exception):
    pass


class EtherscanV2Client:
    """Thin client for Etherscan V2 multi-chain API.

    Base path: https://api.etherscan.io/v2/api?chainid=<id>&...
    """

    def __init__(self, chain_id: int, client: Optional[httpx.Client] = None):
        self.settings = get_settings()
        self.chain_id = chain_id
        self.client = client or httpx.Client(timeout=30)
        self.base_url = "https://api.etherscan.io/v2/api"
        self.limiter = build_limiter(self.settings.redis_url)

    @retry(
        retry=retry_if_exception_type(EtherscanError),
        wait=wait_exponential_jitter(initial=0.5, max=5),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _request(self, params: Dict[str, str]) -> Dict:
        # Respect provider RPS limits
        win = rps_to_window(float(self.settings.etherscan_rps))
        win.key = "etherscan"
        with self.limiter.limit(win.key, win.limit, win.window_seconds):
            req_params = {
                "chainid": str(self.chain_id),
                "apikey": self.settings.etherscan_api_key or "",
                **params,
            }
            resp = self.client.get(self.base_url, params=req_params)
        if resp.status_code == 429:
            raise EtherscanError("Rate limited by Etherscan")
        if resp.status_code != 200:
            raise EtherscanError(f"HTTP {resp.status_code}: {resp.text}")
        data = resp.json()
        status = str(data.get("status", "1"))
        if status != "1" and data.get("message") not in ("OK", "No records found"):
            # Etherscan sometimes returns status=0 with message "No records found"
            raise EtherscanError(f"API Error: {data}")
        return data

    def get_txlist(
        self,
        address: str,
        startblock: Optional[int] = None,
        endblock: Optional[int] = None,
        sort: str = "asc",
    ) -> Dict:
        return self._request(
            {
                "module": "account",
                "action": "txlist",
                "address": address,
                **({"startblock": str(startblock)} if startblock is not None else {}),
                **({"endblock": str(endblock)} if endblock is not None else {}),
                "sort": sort,
            }
        )

    def get_internal_txs(
        self,
        address: str,
        startblock: Optional[int] = None,
        endblock: Optional[int] = None,
        sort: str = "asc",
    ) -> Dict:
        return self._request(
            {
                "module": "account",
                "action": "txlistinternal",
                "address": address,
                **({"startblock": str(startblock)} if startblock is not None else {}),
                **({"endblock": str(endblock)} if endblock is not None else {}),
                "sort": sort,
            }
        )

    def get_logs(
        self,
        address: Optional[str] = None,
        from_block: Optional[int] = None,
        to_block: Optional[int] = None,
        topics: Optional[Iterable[str]] = None,
    ) -> Dict:
        params: Dict[str, str] = {
            "module": "logs",
            "action": "getLogs",
        }
        if address:
            params["address"] = address
        if from_block is not None:
            params["fromBlock"] = str(from_block)
        if to_block is not None:
            params["toBlock"] = str(to_block)
        if topics:
            for i, t in enumerate(topics):
                params[f"topic{i}"] = t
        return self._request(params)

    def iter_txlist_block_windows(
        self,
        address: str,
        start_block: int,
        end_block: int,
        window: int = 10_000,
    ) -> Generator[Dict, None, None]:
        """Yield txlist results over block windows to avoid 10k cap.

        Note: You should de-dup and stop early if gaps are detected.
        """
        cur = start_block
        while cur <= end_block:
            w_end = min(end_block, cur + window - 1)
            yield self.get_txlist(address, startblock=cur, endblock=w_end)
            cur = w_end + 1
