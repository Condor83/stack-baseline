from typing import Dict, Any, List, Optional

from .signatures import (
    UNIV2_SWAP_TOPIC,
    UNIV3_SWAP_TOPIC,
    ERC20_TRANSFER_TOPIC,
    ERC1155_TRANSFER_SINGLE_TOPIC,
    ERC1155_TRANSFER_BATCH_TOPIC,
)


def classify_tx(logs: List[Dict[str, Any]], token_transfers_count: int) -> Dict[str, Any]:
    """Very simple rule-based classification.

    Returns a dict: { primary_label, protocol, confidence, details }
    """
    topics0 = []
    for l in logs:
        t = (l.get("topics") or [])
        if t and isinstance(t[0], str):
            topics0.append(t[0].lower())

    details = {}
    # Swaps
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

