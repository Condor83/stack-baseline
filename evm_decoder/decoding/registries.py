from typing import Dict, Set


# Minimal anchor registries for Ethereum mainnet (chain_id=1)

UNISWAP_V2_ROUTER: Set[str] = {
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
}

UNISWAP_V3_SWAP_ROUTER: Set[str] = {
    "0xe592427a0aece92de3edee1f18e0157c05861564",  # SwapRouter
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",  # SwapRouter02
}

ONEINCH_ROUTER: Set[str] = {
    "0x1111111254eeb25477b68fb85ed929f73a960582",  # 1inch v5
}

ZEROX_EXCHANGE_PROXY: Set[str] = {
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff",
}

COWSWAP_SETTLEMENT: Set[str] = {
    "0x9008d19f58aabd9ed0d60971565aa8510560ab41",
}

ANCHORS_BY_CHAIN: Dict[int, Dict[str, Set[str]]] = {
    1: {
        "univ2_router": UNISWAP_V2_ROUTER,
        "univ3_router": UNISWAP_V3_SWAP_ROUTER,
        "oneinch_router": ONEINCH_ROUTER,
        "0x_proxy": ZEROX_EXCHANGE_PROXY,
        "cowswap_settlement": COWSWAP_SETTLEMENT,
    }
}

