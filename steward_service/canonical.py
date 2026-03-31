from __future__ import annotations

import json
from typing import Any, Dict, List


def canonicalize(value: Any) -> Any:
    """
    Canonical serialization pre-processing for stable hashing.

    - dict keys sorted
    - tuples/sets -> lists (sets sorted by their JSON form)
    - bytes -> {"$bytes_b64": "..."} is intentionally NOT supported in Phase 1A
    """
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [canonicalize(v) for v in value]
    if isinstance(value, tuple):
        return [canonicalize(v) for v in list(value)]
    if isinstance(value, set):
        canon = [canonicalize(v) for v in value]
        canon.sort(key=lambda x: json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return canon
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k in sorted(value.keys(), key=lambda x: str(x)):
            out[str(k)] = canonicalize(value[k])
        return out
    # fallback: stable string representation
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    canon = canonicalize(value)
    return json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

