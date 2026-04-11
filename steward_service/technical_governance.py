"""
Load authoritative technical governance definitions for OpenShell draft-policy actions.

Source of truth: steward_service/data/technical_draft_policy_governance.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .domain import PolicyDefinition, RiskTier
from .registry_catalog import POLICIES


@dataclass(frozen=True)
class ExecuteSpec:
    kind: str
    allow_rationale: str
    step_description: str
    requires_proposed_rule: bool = False
    requires_match: bool = False


@dataclass(frozen=True)
class DraftPolicyActionDefinition:
    steward_action: str
    capability_id: str
    tool_id: str
    base_risk_tier: RiskTier
    approver_role: str
    mutation: bool
    mutation_operator_reason: str
    requires_sandbox_name: bool
    requires_chunk_id: bool
    inspect_chunk_security_notes: bool
    bulk_always_needs_approval: bool
    bulk_approval_reason: str
    execute: ExecuteSpec


@dataclass(frozen=True)
class DefaultDenySpec:
    risk_tier: RiskTier
    approver_role: str
    approval_policy_notes: str
    unsupported_rationale_template: str
    unsupported_requirement_reason: str


@dataclass(frozen=True)
class TechnicalDraftPolicyGovernance:
    version: str
    policy_id: str
    display_name: str
    description: str
    family: str
    default_deny: DefaultDenySpec
    actions_by_steward_action: Dict[str, DraftPolicyActionDefinition]


def _risk(s: str) -> RiskTier:
    return RiskTier(s.strip().lower())


def _load_raw(path: Optional[Path] = None) -> Dict[str, Any]:
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    default = Path(__file__).resolve().parent / "data" / "technical_draft_policy_governance.json"
    return json.loads(default.read_text(encoding="utf-8"))


def load_technical_draft_policy_governance(path: Optional[Path] = None) -> TechnicalDraftPolicyGovernance:
    raw = _load_raw(path)
    dd = raw["default_deny"]
    default_deny = DefaultDenySpec(
        risk_tier=_risk(dd["risk_tier"]),
        approver_role=str(dd["approver_role"]),
        approval_policy_notes=str(dd["approval_policy_notes"]),
        unsupported_rationale_template=str(dd["unsupported_rationale_template"]),
        unsupported_requirement_reason=str(dd["unsupported_requirement_reason"]),
    )
    actions: Dict[str, DraftPolicyActionDefinition] = {}
    for a in raw["actions"]:
        sa = str(a["steward_action"])
        ex = a["execute"]
        bulk = bool(a.get("bulk_always_needs_approval", False))
        if sa.endswith("approve_all") or sa.endswith(".clear"):
            if not bulk:
                raise ValueError(
                    f"{sa} must have bulk_always_needs_approval=true (Phase 1A product rule)"
                )
        exec_spec = ExecuteSpec(
            kind=str(ex["kind"]),
            allow_rationale=str(ex["allow_rationale"]),
            step_description=str(ex["step_description"]),
            requires_proposed_rule=bool(ex.get("requires_proposed_rule", False)),
            requires_match=bool(ex.get("requires_match", False)),
        )
        actions[sa] = DraftPolicyActionDefinition(
            steward_action=sa,
            capability_id=str(a["capability_id"]),
            tool_id=str(a["tool_id"]),
            base_risk_tier=_risk(a["base_risk_tier"]),
            approver_role=str(a["approver_role"]),
            mutation=bool(a["mutation"]),
            mutation_operator_reason=str(
                a.get("mutation_operator_reason", "Draft policy mutations require operator role.")
            ),
            requires_sandbox_name=bool(a["requires_sandbox_name"]),
            requires_chunk_id=bool(a["requires_chunk_id"]),
            inspect_chunk_security_notes=bool(a["inspect_chunk_security_notes"]),
            bulk_always_needs_approval=bulk,
            bulk_approval_reason=str(
                a.get(
                    "bulk_approval_reason",
                    "Bulk draft-policy approve_all/clear requires explicit operator approval (Phase 1A).",
                )
            ),
            execute=exec_spec,
        )
    return TechnicalDraftPolicyGovernance(
        version=str(raw["version"]),
        policy_id=str(raw["policy_id"]),
        display_name=str(raw["display_name"]),
        description=str(raw["description"]),
        family=str(raw["family"]),
        default_deny=default_deny,
        actions_by_steward_action=actions,
    )


def register_technical_draft_policy_policy_metadata(gov: TechnicalDraftPolicyGovernance) -> None:
    POLICIES[gov.policy_id] = PolicyDefinition(
        id=gov.policy_id,
        display_name=gov.display_name,
        description=f"{gov.description} (definitions v{gov.version}; bundled JSON)",
        version=gov.version,
    )


# Module singleton (tests: pass technical_gov= to build_execution_plan, or reset_technical_draft_policy_governance_for_tests)
_TECHNICAL_DRAFT_POLICY: Optional[TechnicalDraftPolicyGovernance] = None


def get_technical_draft_policy_governance() -> TechnicalDraftPolicyGovernance:
    global _TECHNICAL_DRAFT_POLICY
    if _TECHNICAL_DRAFT_POLICY is None:
        _TECHNICAL_DRAFT_POLICY = load_technical_draft_policy_governance()
        register_technical_draft_policy_policy_metadata(_TECHNICAL_DRAFT_POLICY)
    return _TECHNICAL_DRAFT_POLICY


def reset_technical_draft_policy_governance_for_tests() -> None:
    """Clear singleton so next get_* reloads from disk (test isolation)."""
    global _TECHNICAL_DRAFT_POLICY
    _TECHNICAL_DRAFT_POLICY = None
