from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Identity:
    kind: str
    value: str

    def to_public(self) -> str:
        return f"{self.kind}:{self.value}" if self.kind else self.value


def parse_identity(value: Any) -> Optional[Identity]:
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        if ":" in v:
            kind, rest = v.split(":", 1)
            return Identity(kind=kind.strip(), value=rest.strip())
        return Identity(kind="unknown", value=v)
    if isinstance(value, dict):
        kind = str(value.get("kind", "")).strip()
        val = str(value.get("value", "")).strip()
        if not val:
            return None
        return Identity(kind=kind or "unknown", value=val)
    return Identity(kind="unknown", value=str(value))

