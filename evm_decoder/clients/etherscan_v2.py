import time
import json
from typing import Dict, Generator, Iterable, Optional, List

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
        message = str(data.get("message", "")).lower()
        if status != "1":
            # Treat empty-list result as a non-error (common for no data)
            res = data.get("result", None)
            if isinstance(res, list) and len(res) == 0:
                return data
            # Treat common "no data" messages as non-errors
            allowed = (
                "no records found",
                "no transactions found",
                "no internal transactions found",
                "no data found",
            )
            norm = " ".join(message.split())
            if not any(m in norm for m in allowed):
                raise EtherscanError(f"API Error: {data}")
        return data

    def get_txlist(
        self,
        address: str,
        startblock: Optional[int] = None,
        endblock: Optional[int] = None,
        sort: str = "asc",
        page: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict:
        return self._request(
            {
                "module": "account",
                "action": "txlist",
                "address": address,
                **({"startblock": str(startblock)} if startblock is not None else {}),
                **({"endblock": str(endblock)} if endblock is not None else {}),
                "sort": sort,
                **({"page": str(page)} if page is not None else {}),
                **({"offset": str(offset)} if offset is not None else {}),
            }
        )

    def get_internal_txs(
        self,
        address: str,
        startblock: Optional[int] = None,
        endblock: Optional[int] = None,
        sort: str = "asc",
        page: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict:
        return self._request(
            {
                "module": "account",
                "action": "txlistinternal",
                "address": address,
                **({"startblock": str(startblock)} if startblock is not None else {}),
                **({"endblock": str(endblock)} if endblock is not None else {}),
                "sort": sort,
                **({"page": str(page)} if page is not None else {}),
                **({"offset": str(offset)} if offset is not None else {}),
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

    def get_contract_abi(self, address: str) -> Optional[Dict]:
        data = self._request(
            {
                "module": "contract",
                "action": "getabi",
                "address": address,
            }
        )
        result = data.get("result")
        if isinstance(result, str):
            try:
                return {"abi": json.loads(result)}
            except Exception:
                return None
        return None

    def get_source_code(self, address: str) -> Optional[Dict]:
        data = self._request(
            {
                "module": "contract",
                "action": "getsourcecode",
                "address": address,
            }
        )
        res = data.get("result")
        if isinstance(res, list) and res:
            return res[0]
        return None

    def get_tx_receipt(self, tx_hash: str) -> Optional[Dict]:
        """Fetch transaction receipt via Etherscan proxy (JSON-RPC).

        Returns the 'result' object or None on miss/error.
        """
        # Respect provider RPS limits
        with self.limiter.limit("etherscan", self.settings.etherscan_rps, 1):
            req_params = {
                "chainid": str(self.chain_id),
                "apikey": self.settings.etherscan_api_key or "",
                "module": "proxy",
                "action": "eth_getTransactionReceipt",
                "txhash": tx_hash,
            }
            resp = self.client.get(self.base_url, params=req_params)
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        # Expect result to be an object or null; if it's a string error, treat as miss
        res = data.get("result")
        if isinstance(res, dict):
            return res
        return None

    def get_block_number_by_time(self, timestamp: int, closest: str = "before") -> Optional[int]:
        """Map a unix timestamp to the nearest block number using Etherscan.

        closest: 'before'|'after'
        """
        data = self._request(
            {
                "module": "block",
                "action": "getblocknobytime",
                "timestamp": str(timestamp),
                "closest": closest,
            }
        )
        res = data.get("result")
        try:
            return int(res)
        except Exception:
            return None

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

    def iter_txlist_adaptive(
        self,
        address: str,
        start_block: int,
        end_block: int,
        max_items: int = 8000,
        min_span: int = 500,
    ) -> Generator[List[Dict], None, None]:
        """Recursively fetch txlist over [start_block, end_block], splitting ranges
        when a single call returns too many items (>= max_items). This avoids
        hidden truncation caps while keeping calls minimal.

        Yields lists of tx dicts.
        """

        def fetch_range(a: int, b: int) -> Generator[List[Dict], None, None]:
            if a > b:
                return
            data = self.get_txlist(address, startblock=a, endblock=b)
            result = data.get("result") or []
            # If result size is very large and span is still sizable, split
            if isinstance(result, list) and len(result) >= max_items and (b - a) > min_span:
                mid = a + (b - a) // 2
                yield from fetch_range(a, mid)
                yield from fetch_range(mid + 1, b)
            else:
                # return the current chunk
                if isinstance(result, list):
                    yield result

        yield from fetch_range(start_block, end_block)

    def iter_txlist_pages(
        self,
        address: str,
        start_block: int,
        end_block: int,
        page_size: int,
        sort: str = "asc",
    ) -> Generator[List[Dict], None, None]:
        page = 1
        while True:
            data = self.get_txlist(address, startblock=start_block, endblock=end_block, sort=sort, page=page, offset=page_size)
            result = data.get("result") or []
            if not isinstance(result, list) or len(result) == 0:
                break
            yield result
            if len(result) < page_size:
                break
            page += 1

    def iter_internal_txs_pages(
        self,
        address: str,
        start_block: int,
        end_block: int,
        page_size: int,
        sort: str = "asc",
    ) -> Generator[List[Dict], None, None]:
        page = 1
        while True:
            data = self.get_internal_txs(address, startblock=start_block, endblock=end_block, sort=sort, page=page, offset=page_size)
            result = data.get("result") or []
            if not isinstance(result, list) or len(result) == 0:
                break
            yield result
            if len(result) < page_size:
                break
            page += 1

    def iter_internal_txs_adaptive(
        self,
        address: str,
        start_block: int,
        end_block: int,
        max_items: int = 8000,
        min_span: int = 500,
    ) -> Generator[List[Dict], None, None]:
        """Recursively fetch txlistinternal with adaptive splitting."""

        def fetch_range(a: int, b: int) -> Generator[List[Dict], None, None]:
            if a > b:
                return
            data = self.get_internal_txs(address, startblock=a, endblock=b)
            result = data.get("result") or []
            if isinstance(result, list) and len(result) >= max_items and (b - a) > min_span:
                mid = a + (b - a) // 2
                yield from fetch_range(a, mid)
                yield from fetch_range(mid + 1, b)
            else:
                if isinstance(result, list):
                    yield result

        yield from fetch_range(start_block, end_block)
