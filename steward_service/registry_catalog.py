"""
Registry catalog: seeded RoleDefinition, PolicyDefinition, CapabilityDefinition, ToolDefinition.

GET /roles/{id}, /policies/{id}, /capabilities/{id}, /tools/{id} read from here until a persistent
registry store exists. Merge helpers in capability_registry import CAPABILITIES from this module.
"""

from __future__ import annotations

from typing import Dict

from .domain import CapabilityDefinition, PolicyDefinition, RoleDefinition, RiskTier, ToolDefinition

ROLES: Dict[str, RoleDefinition] = {
    "operator": RoleDefinition(
        id="operator",
        display_name="Operator",
        description="Human or trusted operator with elevated draft-policy rights.",
        version="1",
    ),
    "agent": RoleDefinition(
        id="agent",
        display_name="Agent",
        description="Automated actor; mutations typically require approval.",
        version="1",
    ),
    "junior_engineer": RoleDefinition(
        id="junior_engineer",
        display_name="Junior Engineer",
        description="Junior engineer with limited institutional authority for expenditure approvals.",
        version="1",
    ),
}

POLICIES: Dict[str, PolicyDefinition] = {
    "policy.steward.draft_policy_v1": PolicyDefinition(
        id="policy.steward.draft_policy_v1",
        display_name="Steward draft policy (Phase 1A)",
        description="Governance rules for openshell.draft_policy.* actions.",
        version="1",
    ),
}

CAPABILITIES: Dict[str, CapabilityDefinition] = {
    "cap.openshell.draft_policy.read": CapabilityDefinition(
        id="cap.openshell.draft_policy.read",
        resource_family="openshell.draft_policy",
        risk_tier_default=RiskTier.low,
        description="Read draft policy chunks.",
        version="1",
    ),
    "cap.openshell.draft_policy.write": CapabilityDefinition(
        id="cap.openshell.draft_policy.write",
        resource_family="openshell.draft_policy",
        risk_tier_default=RiskTier.medium,
        description="Mutate draft policy (approve/reject/edit/clear/bulk).",
        version="1",
    ),
    "cap.generic": CapabilityDefinition(
        id="cap.generic",
        resource_family="generic",
        risk_tier_default=RiskTier.high,
        description="Unclassified capability.",
        version="1",
    ),
}

TOOLS: Dict[str, ToolDefinition] = {
    "tool.openshell.draft_policy.get": ToolDefinition(
        id="tool.openshell.draft_policy.get",
        steward_action_pattern="openshell.draft_policy.get",
        description="OpenShell GetDraftPolicy",
    ),
    "tool.openshell.draft_policy.mutate": ToolDefinition(
        id="tool.openshell.draft_policy.mutate",
        steward_action_pattern="openshell.draft_policy.*",
        description="OpenShell draft policy mutations",
    ),
    "tool.openshell.draft_policy.approve_matching": ToolDefinition(
        id="tool.openshell.draft_policy.approve_matching",
        steward_action_pattern="openshell.draft_policy.approve_matching",
        description="OpenShell approve matching chunk",
    ),
    "tool.generic": ToolDefinition(
        id="tool.generic",
        steward_action_pattern="*",
        description="Generic tool mapping",
    ),
}
