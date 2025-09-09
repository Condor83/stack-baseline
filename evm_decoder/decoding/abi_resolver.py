from typing import Optional, Dict, Any

from sqlalchemy import select

from ..db import get_engine, session_scope
from ..storage import contracts
from ..clients.abi import ABIResolver
from ..clients.etherscan_v2 import EtherscanV2Client
from ..storage import _hex_to_bytes


def get_contract_row(address: str, chain_id: int) -> Optional[Dict[str, Any]]:
    engine = get_engine()
    if engine is None:
        return None
    addr_b = _hex_to_bytes(address)
    if addr_b is None:
        return None
    with session_scope() as conn:
        row = conn.execute(
            select(
                contracts.c.address,
                contracts.c.chain_id,
                contracts.c.proxy_type,
                contracts.c.implementation,
                contracts.c.abi_json,
                contracts.c.verified_source,
            ).where(contracts.c.chain_id == chain_id, contracts.c.address == addr_b)
        ).fetchone()
        if not row:
            return None
        return dict(row._mapping)


def upsert_contract_abi(address: str, chain_id: int, abi: Any, verified: bool) -> None:
    from sqlalchemy.dialects.postgresql import insert
    engine = get_engine()
    if engine is None:
        return
    addr_b = _hex_to_bytes(address)
    if addr_b is None:
        return
    with session_scope() as conn:
        stmt = insert(contracts).values(
            address=addr_b,
            chain_id=chain_id,
            abi_json=abi,
            verified_source=verified,
        ).on_conflict_do_update(
            index_elements=[contracts.c.chain_id, contracts.c.address],
            set_={"abi_json": abi, "verified_source": verified},
        )
        conn.execute(stmt)


def upsert_proxy_info(address: str, chain_id: int, proxy_type: Optional[str], implementation: Optional[str]) -> None:
    from sqlalchemy.dialects.postgresql import insert
    engine = get_engine()
    if engine is None:
        return
    addr_b = _hex_to_bytes(address)
    impl_b = _hex_to_bytes(implementation) if implementation else None
    with session_scope() as conn:
        stmt = insert(contracts).values(
            address=addr_b,
            chain_id=chain_id,
            proxy_type=proxy_type,
            implementation=impl_b,
        ).on_conflict_do_update(
            index_elements=[contracts.c.chain_id, contracts.c.address],
            set_={"proxy_type": proxy_type, "implementation": impl_b},
        )
        conn.execute(stmt)


def resolve_and_cache_abi(address: str, chain_id: int) -> Optional[Any]:
    row = get_contract_row(address, chain_id)
    if row and row.get("abi_json"):
        return row["abi_json"]
    client = ABIResolver()
    # Try direct ABI
    res = client.resolve_abi(chain_id, address)
    if res and res.get("abi"):
        upsert_contract_abi(address, chain_id, res["abi"], verified=res.get("source") == "sourcify")
        return res["abi"]
    # Check for proxy via Etherscan source code metadata
    esc = EtherscanV2Client(chain_id)
    meta = esc.get_source_code(address)
    if meta and meta.get("Proxy") == "1":
        impl = meta.get("Implementation") or meta.get("Implementation Address")
        upsert_proxy_info(address, chain_id, proxy_type="EIP1967", implementation=impl if isinstance(impl, str) else None)
        if isinstance(impl, str) and impl.startswith("0x"):
            impl_abi = client.resolve_abi(chain_id, impl)
            if impl_abi and impl_abi.get("abi"):
                upsert_contract_abi(address, chain_id, impl_abi["abi"], verified=impl_abi.get("source") == "sourcify")
                # Also upsert implementation row
                upsert_contract_abi(impl, chain_id, impl_abi["abi"], verified=impl_abi.get("source") == "sourcify")
                return impl_abi["abi"]
    return None
