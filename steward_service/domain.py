from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Sequence

from .identity import Identity


class ApprovalRequestState(str, Enum):
    requested = "requested"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    revoked = "revoked"


class ProposalLifecycleState(str, Enum):
    """Steward v2: persisted proposal lifecycle (governance unit)."""

    draft = "draft"
    submitted = "submitted"
    evaluated = "evaluated"
    denied = "denied"
    approval_pending = "approval_pending"
    approved = "approved"
    executing = "executing"
    executed = "executed"
    execution_failed = "execution_failed"
    closed = "closed"


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
    capability_id: str = ""
    tool_id: str = ""


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
    # Steward v2: link to persisted governance proposal row (storage id, not content hash).
    governance_proposal_id: Optional[str] = None
    decision_record_id: Optional[str] = None
    execution_record_id: Optional[str] = None


@dataclass
class GovernanceProposalRecord:
    """
    First-class persisted proposal (v2). Wraps immutable content `Proposal` + lifecycle.
    """

    id: str
    created_at: datetime
    updated_at: datetime
    state: ProposalLifecycleState
    proposal: Proposal
    plan: Optional[ExecutionPlan] = None
    governance_decision: Optional[Decision] = None
    governance_rationale: Optional[str] = None
    linked_audit_ids: List[str] = field(default_factory=list)
    execution_result: Dict[str, Any] = field(default_factory=dict)
    decision_record_id: Optional[str] = None
    execution_record_id: Optional[str] = None


@dataclass
class DecisionRecord:
    """Governance outcome only (separate from runtime execution)."""

    id: str
    created_at: datetime
    governance_proposal_id: str
    content_proposal_id: str
    decision: Decision
    rationale: str
    plan_snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRecord:
    """Runtime execution outcome (OpenShell / downstream)."""

    id: str
    created_at: datetime
    governance_proposal_id: str
    decision_record_id: str
    governance_decision_was_allow: bool
    ok: bool
    result: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalRequestRecord:
    id: str
    created_at: datetime
    updated_at: datetime
    state: ApprovalRequestState
    governance_proposal_id: str
    decision_record_id: str
    decided_by: Optional[str] = None
    notes: str = ""
    expires_at: Optional[datetime] = None


@dataclass
class CandidateActionSetRecord:
    """Persisted candidate evaluation (Steward v2 / Phase 6)."""

    id: str
    created_at: datetime
    updated_at: datetime
    request_summary: Dict[str, Any]
    candidate_ids: List[str]
    evaluations_summary: List[Dict[str, Any]]
    selected_id: Optional[str]
    selected_label: Optional[str]
    selection_rationale: str
    selection_rule: str


@dataclass(frozen=True)
class CapabilityDefinition:
    id: str
    resource_family: str
    risk_tier_default: RiskTier
    description: str = ""
    version: str = "1"


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    steward_action_pattern: str
    description: str = ""


@dataclass(frozen=True)
class RoleDefinition:
    id: str
    display_name: str
    description: str = ""
    version: str = "1"


@dataclass(frozen=True)
class PolicyDefinition:
    """Registry-backed governance policy document (metadata); rules evaluated separately."""

    id: str
    display_name: str
    description: str = ""
    version: str = "1"
