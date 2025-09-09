from typing import Dict, Any, List, Optional

from .signatures import (
    UNIV2_SWAP_TOPIC,
    UNIV3_SWAP_TOPIC,
    ERC20_TRANSFER_TOPIC,
    ERC1155_TRANSFER_SINGLE_TOPIC,
    ERC1155_TRANSFER_BATCH_TOPIC,
)
from .anchors import anchors_for_chain


def classify_tx(
    logs: List[Dict[str, Any]],
    token_transfers_count: int,
    chain_id: int,
    to_address: Optional[str],
    method_id: Optional[str],
    function_name: Optional[str],
) -> Dict[str, Any]:
    """Very simple rule-based classification.

    Returns a dict: { primary_label, protocol, confidence, details }
    """
    topics0 = []
    for l in logs:
        t = (l.get("topics") or [])
        if t and isinstance(t[0], str):
            topics0.append(t[0].lower())

    details = {}
    to_addr_l = (to_address or "").lower()
    anchors = anchors_for_chain(chain_id)
    # Normalize helpers
    fn = (function_name or "").lower()
    # Anchors: routers / settlement / exchange proxy
    if to_addr_l in anchors.get("univ2_router", set()) or to_addr_l in anchors.get("univ3_router", set()):
        return {
            "primary_label": "swap",
            "protocol": "dex_router",
            "confidence": 0.9,
            "details": {"router": to_addr_l, "function": function_name, "selector": method_id},
        }
    if to_addr_l in anchors.get("oneinch_router", set()) or to_addr_l in anchors.get("0x_proxy", set()):
        return {
            "primary_label": "swap",
            "protocol": "aggregator",
            "confidence": 0.85,
            "details": {"router": to_addr_l, "function": function_name, "selector": method_id},
        }
    if to_addr_l in anchors.get("cowswap_settlement", set()):
        return {
            "primary_label": "swap",
            "protocol": "cowswap",
            "confidence": 0.9,
            "details": {"settlement": to_addr_l, "function": function_name},
        }

    # Balancer Vault
    if to_addr_l in anchors.get("balancer_vault", set()):
        if any(x in fn for x in ("batchswap", "swap")):
            return {"primary_label": "swap", "protocol": "balancer", "confidence": 0.9, "details": {"function": function_name}}
        if any(x in fn for x in ("joinpool", "exitpool")):
            return {"primary_label": "liquidity", "protocol": "balancer", "confidence": 0.85, "details": {"function": function_name}}
        return {"primary_label": "balancer", "protocol": "balancer", "confidence": 0.7, "details": {"function": function_name}}

    # ParaSwap Augustus
    if to_addr_l in anchors.get("paraswap_router", set()):
        if any(x in fn for x in ("swap", "multiswap", "megaswap", "simpleswap")):
            return {"primary_label": "swap", "protocol": "paraswap", "confidence": 0.9, "details": {"function": function_name}}
        return {"primary_label": "swap", "protocol": "paraswap", "confidence": 0.8, "details": {"function": function_name}}

    # Aave (Pool / LendingPool)
    if to_addr_l in anchors.get("aave_pool", set()) or to_addr_l in anchors.get("aave_lendingpool", set()):
        if fn.startswith("deposit"):
            return {"primary_label": "defi_deposit", "protocol": "aave", "confidence": 0.9, "details": {"function": function_name}}
        if fn.startswith("withdraw"):
            return {"primary_label": "defi_withdraw", "protocol": "aave", "confidence": 0.9, "details": {"function": function_name}}
        if fn.startswith("borrow"):
            return {"primary_label": "defi_borrow", "protocol": "aave", "confidence": 0.9, "details": {"function": function_name}}
        if fn.startswith("repay"):
            return {"primary_label": "defi_repay", "protocol": "aave", "confidence": 0.9, "details": {"function": function_name}}
        return {"primary_label": "defi", "protocol": "aave", "confidence": 0.7, "details": {"function": function_name}}

    # Euler/Silo simple cues
    if to_addr_l in anchors.get("silo_factory", set()):
        return {"primary_label": "defi_factory", "protocol": "silo", "confidence": 0.7, "details": {"function": function_name}}
    if to_addr_l in anchors.get("euler_evault_factory", set()):
        return {"primary_label": "defi_factory", "protocol": "euler", "confidence": 0.7, "details": {"function": function_name}}

    # Swaps via pool events
    if UNIV2_SWAP_TOPIC in topics0 or UNIV3_SWAP_TOPIC in topics0:
        return {
            "primary_label": "swap",
            "protocol": "dex_amm",
            "confidence": 0.8,
            "details": details,
        }
    # Transfers only
    if token_transfers_count > 0:
        return {
            "primary_label": "transfers",
            "protocol": None,
            "confidence": 0.7,
            "details": {"transfers": token_transfers_count},
        }
    # ERC-1155 only
    if ERC1155_TRANSFER_SINGLE_TOPIC in topics0 or ERC1155_TRANSFER_BATCH_TOPIC in topics0:
        return {
            "primary_label": "nft_transfers",
            "protocol": None,
            "confidence": 0.7,
            "details": {},
        }
    return {
        "primary_label": "other",
        "protocol": None,
        "confidence": 0.4,
        "details": {},
    }
