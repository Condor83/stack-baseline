import json
import os
from functools import lru_cache
from typing import Dict, Set

from ..config import get_settings


@lru_cache(maxsize=1)
def _load_anchors() -> Dict[int, Dict[str, Set[str]]]:
    """Load anchors from a JSON file; fallback to packaged defaults.

    Returns a mapping: chain_id -> { label -> set(addresses) }
    """
    settings = get_settings()
    paths = []
    if settings and getattr(settings, "env", None):
        pass
    # Env override
    env_path = os.getenv("ANCHORS_FILE")
    if env_path:
        paths.append(env_path)
    # Project config default
    paths.append(os.path.join(os.getcwd(), "config", "anchors.json"))
    # Packaged default
    pkg_default = os.path.join(os.path.dirname(__file__), "anchors.default.json")
    paths.append(pkg_default)

    data = None
    for p in paths:
        try:
            if os.path.exists(p):
                with open(p, "r") as f:
                    data = json.load(f)
                    break
        except Exception:
            continue
    if not isinstance(data, dict):
        return {}
    out: Dict[int, Dict[str, Set[str]]] = {}
    for chain_str, labels in data.items():
        try:
            cid = int(chain_str)
        except Exception:
            continue
        out[cid] = {}
        if isinstance(labels, dict):
            for k, arr in labels.items():
                try:
                    addrs = {str(a).lower() for a in (arr or [])}
                except Exception:
                    addrs = set()
                out[cid][k] = addrs
    return out


def anchors_for_chain(chain_id: int) -> Dict[str, Set[str]]:
    anchors = _load_anchors()
    return anchors.get(chain_id, {})


def is_anchor(chain_id: int, label: str, address: str) -> bool:
    return address.lower() in anchors_for_chain(chain_id).get(label, set())

