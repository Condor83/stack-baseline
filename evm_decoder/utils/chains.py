from typing import Optional


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
EEE_ADDRESS = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"


def is_native_address(addr: str) -> bool:
    a = addr.lower()
    return a in (ZERO_ADDRESS, EEE_ADDRESS, "native")


def coingecko_platform(chain_id: int) -> Optional[str]:
    return {
        1: "ethereum",
        42161: "arbitrum-one",
        10: "optimistic-ethereum",
        8453: "base",
        137: "polygon-pos",
        56: "binance-smart-chain",
        43114: "avalanche",
        324: "zksync-era",
        59144: "linea",
        # 146 unknown on CG platform mapping; return None
    }.get(chain_id)


def coingecko_native_coin_id(chain_id: int) -> Optional[str]:
    return {
        1: "ethereum",
        42161: "ethereum",  # ETH on L2s
        10: "ethereum",
        8453: "ethereum",
        137: "matic-network",
        56: "binancecoin",
        43114: "avalanche-2",
        324: "ethereum",
        59144: "ethereum",
    }.get(chain_id)


def llama_chain_slug(chain_id: int) -> Optional[str]:
    return {
        1: "ethereum",
        42161: "arbitrum",
        10: "optimism",
        8453: "base",
        137: "polygon",
        56: "bsc",
        43114: "avax",
        324: "zksync",  # commonly used slug
        59144: "linea",
    }.get(chain_id)

