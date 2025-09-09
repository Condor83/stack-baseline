from typing import Dict, Any, Optional, Tuple, List

from eth_utils import keccak, to_bytes


def fn_selector_from_abi(abi_entry: Dict[str, Any]) -> Optional[bytes]:
    if abi_entry.get("type") != "function":
        return None
    name = abi_entry.get("name")
    inputs = abi_entry.get("inputs", [])
    if not name:
        return None
    sig = name + "(" + ",".join(i.get("type", "") for i in inputs) + ")"
    return keccak(text=sig)[:4]


def event_topic0_from_abi(abi_entry: Dict[str, Any]) -> Optional[bytes]:
    if abi_entry.get("type") != "event":
        return None
    name = abi_entry.get("name")
    inputs = abi_entry.get("inputs", [])
    if not name:
        return None
    sig = name + "(" + ",".join(i.get("type", "") for i in inputs) + ")"
    return keccak(text=sig)


def build_abi_index(abi: List[Dict[str, Any]]) -> Tuple[Dict[bytes, Dict[str, Any]], Dict[bytes, Dict[str, Any]]]:
    fns: Dict[bytes, Dict[str, Any]] = {}
    evs: Dict[bytes, Dict[str, Any]] = {}
    for e in abi or []:
        if e.get("type") == "function":
            sel = fn_selector_from_abi(e)
            if sel is not None:
                fns[sel] = e
        elif e.get("type") == "event":
            t0 = event_topic0_from_abi(e)
            if t0 is not None:
                evs[t0] = e
    return fns, evs

