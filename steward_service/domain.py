from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Sequence

from .identity import Identity


class Decision(str, Enum):
    allow = "allow"
    deny = "deny"
    needs_approval = "needs_approval"


class AuthorizationDecision(str, Enum):
    allow = "allow"
    deny = "deny"


class ApprovalState(str, Enum):
    not_required = "not_required"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ActionType(str, Enum):
    generic = "generic"
    openshell_draft_policy = "openshell_draft_policy"


class RiskTier(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    action_type: ActionType
    action: str
    purpose: str
    role: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyRule:
    name: str
    endpoints: Sequence[Dict[str, Any]]
    binaries: Sequence[Dict[str, Any]]


ApprovalRequirementType = Literal["operator", "security_review"]


@dataclass(frozen=True)
class ApprovalRequirement:
    requirement: ApprovalRequirementType
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


ApproverRole = Literal["operator", "security"]


@dataclass(frozen=True)
class ApprovalPolicy:
    approver_role: ApproverRole
    auto_allow: bool
    notes: str = ""


@dataclass(frozen=True)
class ExecutionStep:
    step: int
    type: str
    description: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionPlan:
    # External/API-facing combined view.
    decision: Decision
    # Internal split concepts.
    authorization_decision: AuthorizationDecision
    approval_state: ApprovalState
    rationale: str
    risk_tier: RiskTier = RiskTier.low
    approval_policy: Optional[ApprovalPolicy] = None
    requirements: List[ApprovalRequirement] = field(default_factory=list)
    steps: List[ExecutionStep] = field(default_factory=list)


AuditKind = Literal["authorize", "simulate", "execute"]
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]


@dataclass(frozen=True)
class AuditRecord:
    id: str
    created_at: datetime
    kind: AuditKind
    proposal: Proposal
    proposal_id: str
    action_type: ActionType
    requested_by: Optional[Identity] = None
    approved_by: Optional[Identity] = None
    approval_status: ApprovalStatus = "not_required"
    governance_basis: List[str] = field(default_factory=list)
    external_refs: List[Dict[str, Any]] = field(default_factory=list)
    decision: Optional[Decision] = None
    rationale: Optional[str] = None
    plan: Optional[ExecutionPlan] = None
    result: Dict[str, Any] = field(default_factory=dict)
