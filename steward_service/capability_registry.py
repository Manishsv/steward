from __future__ import annotations

from typing import Tuple

from .domain import RiskTier
from .registry_catalog import CAPABILITIES, TOOLS


def capability_and_tool_for_action(action: str) -> Tuple[str, str]:
    a = action.strip().lower()
    if "draft_policy.get" in a:
        return "cap.openshell.draft_policy.read", "tool.openshell.draft_policy.get"
    if "approve_matching" in a:
        return "cap.openshell.draft_policy.write", "tool.openshell.draft_policy.approve_matching"
    if "draft_policy" in a:
        return "cap.openshell.draft_policy.write", "tool.openshell.draft_policy.mutate"
    return "cap.generic", "tool.generic"


def _risk_rank(tier: RiskTier) -> int:
    return {RiskTier.low: 0, RiskTier.medium: 1, RiskTier.high: 2}[tier]


def _risk_max(a: RiskTier, b: RiskTier) -> RiskTier:
    return a if _risk_rank(a) >= _risk_rank(b) else b


def capability_default_risk_for_id(capability_id: str) -> RiskTier:
    c = CAPABILITIES.get(capability_id)
    return c.risk_tier_default if c else RiskTier.high


def merge_action_and_capability_risk(action_risk: RiskTier, capability_id: str) -> RiskTier:
    return _risk_max(action_risk, capability_default_risk_for_id(capability_id))


__all__ = [
    "CAPABILITIES",
    "TOOLS",
    "capability_and_tool_for_action",
    "capability_default_risk_for_id",
    "merge_action_and_capability_risk",
]
