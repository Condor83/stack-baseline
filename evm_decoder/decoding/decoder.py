from typing import Dict, Any, List, Optional, Tuple

from eth_abi import abi as eth_abi

from ..db import get_engine, session_scope
from ..storage import logs as logs_tbl
from ..decoding.abi_resolver import resolve_and_cache_abi
from .abi_utils import build_abi_index
from ..storage import _hex_to_bytes


def decode_call_input(to_address: Optional[str], input_bytes: Optional[bytes]) -> Optional[Dict[str, Any]]:
    if to_address is None or input_bytes is None or len(input_bytes) < 4:
        return None
    abi = resolve_and_cache_abi(to_address, _infer_chain_id())  # chain id inference placeholder
    if not abi:
        return None
    fn_index, _ = build_abi_index(abi)
    selector = input_bytes[:4]
    fn = fn_index.get(selector)
    if not fn:
        return None
    types = [inp.get("type", "bytes") for inp in fn.get("inputs", [])]
    try:
        args_encoded = input_bytes[4:]
        values = list(eth_abi.decode(types, args_encoded)) if types else []
        args_out = []
        for i, inp in enumerate(fn.get("inputs", [])):
            args_out.append({"name": inp.get("name"), "type": inp.get("type"), "value": _to_jsonable(values[i]) if i < len(values) else None})
        return {
            "name": fn.get("name"),
            "selector": "0x" + selector.hex(),
            "args": args_out,
        }
    except Exception:
        return {"name": fn.get("name"), "selector": "0x" + selector.hex(), "args": None}


def decode_and_store_logs(chain_id: int, tx_id: int) -> int:
    engine = get_engine()
    if engine is None:
        return 0
    count = 0
    with engine.begin() as conn:
        rows = conn.execute(logs_tbl.select().where(logs_tbl.c.tx_id == tx_id)).fetchall()
        for r in rows:
            addr = r.address
            topics_blob = r.topics
            data_blob = r.data
            if addr is None or topics_blob is None:
                continue
            try:
                address_hex = "0x" + (addr.tobytes().hex() if isinstance(addr, memoryview) else addr.hex())
                topics_str = (topics_blob.tobytes().decode() if isinstance(topics_blob, memoryview) else topics_blob.decode())
                topics = topics_str.split("|") if topics_str else []
                data_hex = "0x" + (data_blob.tobytes().hex() if isinstance(data_blob, memoryview) else (data_blob.hex() if data_blob is not None else ""))
            except Exception:
                continue
            dec = _decode_event_for_address(chain_id, address_hex, topics, data_hex)
            if dec is not None:
                try:
                    conn.execute(
                        logs_tbl.update().where(
                            logs_tbl.c.id == r.id
                        ).values(decoded_event=dec)
                    )
                    count += 1
                except Exception:
                    pass
    return count


def _decode_event_for_address(chain_id: int, address: str, topics: List[str], data_hex: str) -> Optional[Dict[str, Any]]:
    abi = resolve_and_cache_abi(address, chain_id)
    if not abi or not topics:
        return None
    _, ev_index = build_abi_index(abi)
    try:
        t0 = bytes.fromhex(topics[0].removeprefix("0x"))
    except Exception:
        return None
    ev = ev_index.get(t0)
    if not ev:
        return None
    # Build arg list
    inputs = ev.get("inputs", [])
    non_indexed_types = [i["type"] for i in inputs if not i.get("indexed")]
    non_indexed_names = [i.get("name") for i in inputs if not i.get("indexed")]
    indexed_inputs = [i for i in inputs if i.get("indexed")]
    # Decode non-indexed from data
    args_out: Dict[str, Any] = {}
    try:
        data_bytes = bytes.fromhex(data_hex.removeprefix("0x")) if data_hex else b""
        if non_indexed_types and data_bytes:
            values = list(eth_abi.decode(non_indexed_types, data_bytes))
        else:
            values = []
        for name, val in zip(non_indexed_names, values):
            args_out[name or "arg"] = _to_jsonable(val)
    except Exception:
        pass
    # Parse indexed from topics[1:]
    for idx, inp in enumerate(indexed_inputs):
        name = inp.get("name") or f"indexed_{idx}"
        typ = inp.get("type")
        if len(topics) > (idx + 1):
            raw = topics[idx + 1]
            try:
                b = bytes.fromhex(raw.removeprefix("0x"))
                # For address, take last 20 bytes
                if typ == "address" and len(b) >= 32:
                    args_out[name] = "0x" + b[-20:].hex()
                else:
                    args_out[name] = "0x" + b.hex()
            except Exception:
                args_out[name] = raw
    return {"name": ev.get("name"), "args": args_out}


def _to_jsonable(val: Any) -> Any:
    if isinstance(val, (bytes, bytearray)):
        return "0x" + bytes(val).hex()
    if isinstance(val, (list, tuple)):
        return [_to_jsonable(x) for x in val]
    try:
        # ints / decimals / strings are jsonable
        return val
    except Exception:
        return str(val)


def _infer_chain_id() -> int:
    # Placeholder; decode_call_input should be provided chain_id by caller in future
    return 1

