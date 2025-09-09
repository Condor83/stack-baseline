import json
from typing import Optional, Dict, Any

import httpx

from ..config import get_settings
from ..rate_limiter import build_limiter, rps_to_window
from .etherscan_v2 import EtherscanV2Client


class ABIResolver:
    def __init__(self):
        self.settings = get_settings()
        self.http = httpx.Client(timeout=30)
        self.limiter = build_limiter(self.settings.redis_url)

    def _sourcify_urls(self, chain_id: int, address: str):
        addr_lower = address.lower()
        return [
            f"https://repo.sourcify.dev/contracts/full_match/{chain_id}/{addr_lower}/metadata.json",
            f"https://repo.sourcify.dev/contracts/partial_match/{chain_id}/{addr_lower}/metadata.json",
            f"https://sourcify.dev/server/repository/contracts/full_match/{chain_id}/{addr_lower}/metadata.json",
            f"https://sourcify.dev/server/repository/contracts/partial_match/{chain_id}/{addr_lower}/metadata.json",
        ]

    def fetch_from_sourcify(self, chain_id: int, address: str) -> Optional[Dict[str, Any]]:
        win = rps_to_window(2.0)
        win.key = "sourcify"
        for url in self._sourcify_urls(chain_id, address):
            try:
                with self.limiter.limit(win.key, win.limit, win.window_seconds):
                    resp = self.http.get(url)
                if resp.status_code == 200:
                    meta = resp.json()
                    abi = meta.get("output", {}).get("abi") or meta.get("abi")
                    if abi:
                        return {"abi": abi, "source": "sourcify", "metadata": meta}
            except Exception:
                continue
        return None

    def fetch_from_etherscan(self, chain_id: int, address: str) -> Optional[Dict[str, Any]]:
        client = EtherscanV2Client(chain_id)
        data = client.get_contract_abi(address)
        if data and isinstance(data.get("abi"), list):
            return {"abi": data["abi"], "source": "etherscan"}
        return None

    def fetch_from_4byte(self, selector: str) -> Optional[str]:
        # Fetch a function signature for a 4-byte selector; returns best guess signature string
        try:
            url = f"https://www.4byte.directory/api/v1/signatures/?hex_signature={selector}"
            resp = self.http.get(url, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results") or []
                if results:
                    # Take most common or first
                    return results[0].get("text_signature")
        except Exception:
            pass
        return None

    def resolve_abi(self, chain_id: int, address: str) -> Optional[Dict[str, Any]]:
        # Try Sourcify first
        res = self.fetch_from_sourcify(chain_id, address)
        if res:
            return res
        # Fallback Etherscan
        res = self.fetch_from_etherscan(chain_id, address)
        if res:
            return res
        return None

