"""First-class extraction of governance-relevant fields from proposal context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .identity import Identity, parse_identity


@dataclass(frozen=True)
class GovernanceContext:
    """Stable view of identity and channel metadata attached to a proposal."""

    requested_by: Optional[Identity]
    approved_by: Optional[Identity]
    channel: Optional[str]
    external_refs: List[Any]

    @staticmethod
    def from_proposal_context(context: Optional[Dict[str, Any]]) -> "GovernanceContext":
        ctx = context or {}
        refs = ctx.get("external_refs")
        ref_list: List[Any] = refs if isinstance(refs, list) else []
        ch = ctx.get("channel")
        channel = str(ch).strip() if ch is not None and str(ch).strip() else None
        return GovernanceContext(
            requested_by=parse_identity(ctx.get("requested_by")),
            approved_by=parse_identity(ctx.get("approved_by")),
            channel=channel,
            external_refs=ref_list,
        )
