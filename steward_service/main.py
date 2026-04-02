from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Dict, Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .audit_store import InMemoryAuditStore
from .canonical import canonical_json_bytes
from .effective_policy import resolve_effective_policy as resolve_effective_policy_record
from .approval_store import InMemoryApprovalStore
from .domain import ApprovalRequestRecord
from .domain import ApprovalRequestState
from .domain import ApprovalState
from .domain import ApprovalStatus
from .domain import AuditRecord as InternalAuditRecord
from .domain import ActionType as InternalActionType
from .domain import AuthorizationDecision
from .domain import CandidateActionSetRecord
from .domain import Decision as DomainDecision
from .domain import DecisionRecord
from .domain import ExecutionPlan
from .domain import ExecutionRecord
from .domain import GovernanceProposalRecord
from .domain import Proposal as InternalProposal
from .domain import ProposalLifecycleState
from .decision_store import InMemoryDecisionStore
from .execution_store import InMemoryExecutionStore
from .identity import parse_identity
from .governance import build_execution_plan, execute_plan, generated_external_refs
from .governance_context import GovernanceContext
from .openshell_client import create_openshell_client
from .proposal_service import (
    apply_evaluation,
    create_draft,
    evaluate_content,
    link_audit,
    mark_executed,
    mark_executing,
    mark_proposal_approved_after_external_ok,
    mark_proposal_denied_after_approval_rejection,
    submit,
)
from .proposal_store import InMemoryProposalStore
from .candidate_set_store import InMemoryCandidateSetStore
from .registry_catalog import CAPABILITIES, POLICIES, ROLES, TOOLS


class Decision(str, Enum):
    allow = "allow"
    deny = "deny"
    needs_approval = "needs_approval"


class ActionProposal(BaseModel):
    action: str = Field(..., description="Logical action name, e.g. 'exec', 'policy_update'.")
    purpose: str = Field(..., min_length=1)
    role: Optional[str] = Field(default=None, description="Actor role, e.g. 'agent', 'operator'.")
    context: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AuthorizeRequest(BaseModel):
    proposal: ActionProposal


class AuthorizeResponse(BaseModel):
    decision: Decision
    rationale: str
    audit_id: str


class SimulateRequest(BaseModel):
    proposal: ActionProposal


class SimulateResponse(BaseModel):
    audit_id: str
    simulation: Dict[str, Any]


class ExecuteRequest(BaseModel):
    proposal: ActionProposal


class ExecuteResponse(BaseModel):
    audit_id: str
    status: Literal["executed"]
    result: Dict[str, Any]


class AuditRecord(BaseModel):
    id: str
    created_at: datetime
    kind: Literal["authorize", "simulate", "execute"]
    proposal: ActionProposal
    decision: Optional[Decision] = None
    rationale: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    governance_proposal_id: Optional[str] = None
    decision_record_id: Optional[str] = None
    execution_record_id: Optional[str] = None
    operator_hints: Dict[str, str] = Field(default_factory=dict)

class Candidate(BaseModel):
    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    type: Optional[Literal["diagnostic", "remediation", "administrative"]] = None
    proposal: ActionProposal


class EvaluateCandidatesRequest(BaseModel):
    candidates: list[Candidate]


class CandidateEvaluation(BaseModel):
    id: str
    label: str
    decision: Decision
    rationale: str
    audit_id: str
    risk_tier: str

class CandidateSelection(BaseModel):
    selected_id: Optional[str] = None
    selected_label: Optional[str] = None
    decision: Optional[Decision] = None
    rationale: str
    rule: str

class EvaluateCandidatesResponse(BaseModel):
    evaluations: list[CandidateEvaluation]
    selection: CandidateSelection


class CreateProposalRequest(BaseModel):
    proposal: ActionProposal
    submit: bool = False
    evaluate: bool = False


class ProposalRecordResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    state: str
    proposal: ActionProposal
    governance_decision: Optional[str] = None
    governance_rationale: Optional[str] = None
    plan: Optional[Dict[str, Any]] = None
    linked_audit_ids: list[str] = Field(default_factory=list)
    execution_result: Dict[str, Any] = Field(default_factory=dict)
    decision_record_id: Optional[str] = None
    execution_record_id: Optional[str] = None


class DecisionRecordResponse(BaseModel):
    id: str
    created_at: datetime
    governance_proposal_id: str
    content_proposal_id: str
    decision: str
    rationale: str
    plan_snapshot: Dict[str, Any] = Field(default_factory=dict)


class ExecutionRecordResponse(BaseModel):
    id: str
    created_at: datetime
    governance_proposal_id: str
    decision_record_id: str
    governance_decision_was_allow: bool
    ok: bool
    result: Dict[str, Any] = Field(default_factory=dict)


class CreateApprovalRequestBody(BaseModel):
    governance_proposal_id: str
    expires_at: Optional[datetime] = None


class ApprovalRequestResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    state: str
    governance_proposal_id: str
    decision_record_id: str
    expires_at: Optional[datetime] = None


class ApprovalDecisionBody(BaseModel):
    decision: Literal["approved", "rejected"]
    decided_by: Optional[str] = None


class EffectivePolicyResolveRequest(BaseModel):
    role: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class EffectivePolicyResponse(BaseModel):
    autonomy_ceiling: str
    constitution_version: str
    sources: Dict[str, str]


class CandidateSetEvaluateResponse(BaseModel):
    candidate_set_id: str
    evaluations: list[CandidateEvaluation]
    selection: CandidateSelection


class CandidateSetRecordResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    request_summary: Dict[str, Any]
    candidate_ids: list[str]
    evaluations_summary: list[Dict[str, Any]]
    selected_id: Optional[str]
    selected_label: Optional[str]
    selection_rationale: str
    selection_rule: str


class CapabilityDefinitionResponse(BaseModel):
    id: str
    resource_family: str
    risk_tier_default: str
    description: str = ""
    version: str = "1"


class ToolDefinitionResponse(BaseModel):
    id: str
    steward_action_pattern: str
    description: str = ""


class RoleDefinitionResponse(BaseModel):
    id: str
    display_name: str
    description: str = ""
    version: str = "1"


class PolicyDefinitionResponse(BaseModel):
    id: str
    display_name: str
    description: str = ""
    version: str = "1"


_audit = InMemoryAuditStore()
_proposals = InMemoryProposalStore()
_decisions = InMemoryDecisionStore()
_executions = InMemoryExecutionStore()
_approvals = InMemoryApprovalStore()
_candidate_sets = InMemoryCandidateSetStore()
_openshell = create_openshell_client()


def _plan_to_payload(plan: Optional[ExecutionPlan]) -> Optional[Dict[str, Any]]:
    if plan is None:
        return None
    return {
        "decision": plan.decision.value,
        "authorization_decision": plan.authorization_decision.value,
        "approval_state": plan.approval_state.value,
        "rationale": plan.rationale,
        "risk_tier": plan.risk_tier.value,
        "capability_id": plan.capability_id,
        "tool_id": plan.tool_id,
        "approval_policy": asdict(plan.approval_policy) if plan.approval_policy else None,
        "requirements": [asdict(r) for r in plan.requirements],
        "steps": [asdict(s) for s in plan.steps],
    }


def _governance_proposal_to_response(rec: GovernanceProposalRecord) -> ProposalRecordResponse:
    return ProposalRecordResponse(
        id=rec.id,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        state=rec.state.value,
        proposal=ActionProposal(
            action=rec.proposal.action,
            purpose=rec.proposal.purpose,
            role=rec.proposal.role,
            context=dict(rec.proposal.context),
            parameters=dict(rec.proposal.parameters),
        ),
        governance_decision=rec.governance_decision.value if rec.governance_decision else None,
        governance_rationale=rec.governance_rationale,
        plan=_plan_to_payload(rec.plan),
        linked_audit_ids=list(rec.linked_audit_ids),
        execution_result=dict(rec.execution_result),
        decision_record_id=rec.decision_record_id,
        execution_record_id=rec.execution_record_id,
    )


def _persist_decision(gp_id: str, content_proposal_id: str, plan: ExecutionPlan) -> str:
    dr_id = _decisions.new_id()
    dr = DecisionRecord(
        id=dr_id,
        created_at=_decisions.now(),
        governance_proposal_id=gp_id,
        content_proposal_id=content_proposal_id,
        decision=plan.decision,
        rationale=plan.rationale,
        plan_snapshot=_plan_to_payload(plan) or {},
    )
    _decisions.put(dr)
    gp = _proposals.get(gp_id)
    if gp:
        gp.decision_record_id = dr_id
        gp.updated_at = _proposals.now()
        _proposals.put(gp)
    return dr_id


def _persist_execution(
    gp_id: str,
    decision_record_id: str,
    plan_allow: bool,
    ok: bool,
    result: Dict[str, Any],
) -> str:
    er_id = _executions.new_id()
    er = ExecutionRecord(
        id=er_id,
        created_at=_executions.now(),
        governance_proposal_id=gp_id,
        decision_record_id=decision_record_id,
        governance_decision_was_allow=plan_allow,
        ok=ok,
        result=dict(result),
    )
    _executions.put(er)
    gp = _proposals.get(gp_id)
    if gp:
        gp.execution_record_id = er_id
        gp.updated_at = _proposals.now()
        _proposals.put(gp)
    return er_id


def _link_proposal_audit(gp_id: str, audit_id: str) -> None:
    gp = _proposals.get(gp_id)
    if gp:
        link_audit(gp, audit_id)
        _proposals.put(gp)


def _maybe_resume_proposal(
    internal: InternalProposal,
    context: Dict[str, Any],
) -> Optional[tuple[GovernanceProposalRecord, ExecutionPlan]]:
    rid = context.get("steward_resume_proposal_id")
    if not isinstance(rid, str) or not rid.strip():
        return None
    # Same resolution rules as POST /approval-requests (storage id, decision_record_id, or content hash).
    gp = _resolve_governance_proposal_for_approval(rid)
    if gp is None or gp.plan is None:
        return None
    if gp.proposal.proposal_id != internal.proposal_id:
        return None
    return gp, gp.plan


def _effective_plan_for_execute(
    plan: ExecutionPlan,
    gp_id: str,
    context: Dict[str, Any],
) -> tuple[ExecutionPlan, bool]:
    if plan.decision != DomainDecision.needs_approval:
        return plan, False
    ar_id = context.get("approval_request_id")
    if not isinstance(ar_id, str) or not ar_id.strip():
        return plan, False
    ar = _approvals.get(ar_id.strip())
    if ar is None or ar.governance_proposal_id != gp_id:
        return plan, False
    if ar.state != ApprovalRequestState.approved:
        return plan, False
    now = datetime.now(timezone.utc)
    if ar.expires_at is not None and ar.expires_at <= now:
        return plan, False
    decided = ar.decided_by.strip() if isinstance(ar.decided_by, str) and ar.decided_by.strip() else "operator"
    rationale = (
        f"Approved via approval request {ar_id.strip()} (decided_by={decided}); "
        "requirements satisfied, executing with approval."
    )
    return (
        replace(
            plan,
            decision=DomainDecision.allow,
            authorization_decision=AuthorizationDecision.allow,
            approval_state=ApprovalState.approved,
            rationale=rationale,
        ),
        True,
    )


def _context_for_proposal_id(context: Dict[str, Any]) -> Dict[str, Any]:
    """Exclude Steward control-plane keys so resume/approval context does not change proposal_id."""
    skip = frozenset({"steward_resume_proposal_id", "approval_request_id"})
    return {k: v for k, v in context.items() if k not in skip}


def _stable_proposal_id(p: ActionProposal) -> str:
    payload = {
        "action": p.action,
        "purpose": p.purpose,
        "role": p.role,
        "context": _context_for_proposal_id(dict(p.context)),
        "parameters": p.parameters,
    }
    raw = canonical_json_bytes(payload)
    return hashlib.sha256(raw).hexdigest()


def _action_type(action: str) -> InternalActionType:
    a = action.strip().lower()
    if a.startswith("openshell.draft_policy."):
        return InternalActionType.openshell_draft_policy
    return InternalActionType.generic


def _operator_hints_for_audit(record: InternalAuditRecord) -> Dict[str, str]:
    """Stable, operator-oriented strings for TUI clients (NemoClaw); backward-compatible extra fields."""
    hints: Dict[str, str] = {}
    if record.governance_proposal_id:
        hints["governance_proposal_id"] = record.governance_proposal_id
    if record.decision_record_id:
        hints["decision_record_id"] = record.decision_record_id
    if record.execution_record_id:
        hints["execution_record_id"] = record.execution_record_id
    if (
        record.kind == "authorize"
        and record.decision is not None
        and record.decision.value == "needs_approval"
    ):
        hints["nemoclaw_approval_complete"] = f"/nemoclaw approval complete {record.id}"
        hints["why"] = "Governance requires operator approval before this action can execute."
    return hints


def _to_internal(p: ActionProposal) -> InternalProposal:
    return InternalProposal(
        proposal_id=_stable_proposal_id(p),
        action_type=_action_type(p.action),
        action=p.action,
        purpose=p.purpose,
        role=p.role,
        context=p.context,
        parameters=p.parameters,
    )


def _to_public_audit(record: InternalAuditRecord) -> AuditRecord:
    proposal = ActionProposal(
        action=record.proposal.action,
        purpose=record.proposal.purpose,
        role=record.proposal.role,
        context=dict(record.proposal.context),
        parameters=dict(record.proposal.parameters),
    )
    return AuditRecord(
        id=record.id,
        created_at=record.created_at,
        kind=record.kind,
        proposal=proposal,
        decision=Decision(record.decision.value) if record.decision is not None else None,
        rationale=record.rationale,
        payload=_audit.to_public_payload(record),
        governance_proposal_id=record.governance_proposal_id,
        decision_record_id=record.decision_record_id,
        execution_record_id=record.execution_record_id,
        operator_hints=_operator_hints_for_audit(record),
    )


app = FastAPI(title="Steward", version="0.0.1")

def _execute_user_hint(*, decision: str, rationale: str, result: Dict[str, Any]) -> str:
    """
    Provide a user-facing hint for execute failures.

    Keep this decision-aware and error-aware because /action/execute can fail due to:
    - governance gating (deny / needs_approval)
    - downstream runtime errors (OpenShell/gRPC)
    """
    d = (decision or "").strip().lower()
    r = (rationale or "").strip().lower()
    err = str(result.get("error", "")).strip().lower() if isinstance(result, dict) else ""

    if d == "needs_approval":
        return (
            "Approval is required before this action can run. "
            "Next: request an operator approval (or update role/context) and retry."
        )

    if d == "deny":
        if "unsupported action" in r or "no governance policy" in r:
            return (
                "This action is unsupported: no governance policy exists for it. "
                "Next: use a supported action or add an explicit policy in Steward."
            )
        return "This action was denied by governance policy. Next: adjust the request and retry."

    # decision == allow but execution failed
    if err == "external_call_failed":
        return (
            "Governance allowed the action, but OpenShell/runtime execution failed. "
            "Next: verify OpenShell connectivity (mTLS), and validate sandbox/chunk identifiers."
        )
    if err == "not_allowed":
        return (
            "This action was not allowed to execute. "
            "Next: review the governance decision and requirements, then retry."
        )

    return (
        "Execution failed after authorization. "
        "Next: retry with operator details and inspect the audit record for diagnostics."
    )


@app.post("/proposals", response_model=ProposalRecordResponse)
def create_proposal(req: CreateProposalRequest) -> ProposalRecordResponse:
    internal = _to_internal(req.proposal)
    rec = create_draft(_proposals, internal)
    if req.submit:
        submit(_proposals, rec)
    if req.evaluate:
        rec = _proposals.get(rec.id) or rec
        if rec.state.value == "draft":
            submit(_proposals, rec)
            rec = _proposals.get(rec.id) or rec
        plan = build_execution_plan(internal, _openshell)
        apply_evaluation(_proposals, rec, plan)
        rec = _proposals.get(rec.id) or rec
        if rec.plan is not None:
            _persist_decision(rec.id, internal.proposal_id, rec.plan)
            rec = _proposals.get(rec.id) or rec
    return _governance_proposal_to_response(rec)


@app.get("/decision-records/{record_id}", response_model=DecisionRecordResponse)
def get_decision_record(record_id: str) -> DecisionRecordResponse:
    dr = _decisions.get(record_id)
    if dr is None:
        raise HTTPException(status_code=404, detail="decision record not found")
    return DecisionRecordResponse(
        id=dr.id,
        created_at=dr.created_at,
        governance_proposal_id=dr.governance_proposal_id,
        content_proposal_id=dr.content_proposal_id,
        decision=dr.decision.value,
        rationale=dr.rationale,
        plan_snapshot=dr.plan_snapshot,
    )


@app.get("/execution-records/{record_id}", response_model=ExecutionRecordResponse)
def get_execution_record(record_id: str) -> ExecutionRecordResponse:
    er = _executions.get(record_id)
    if er is None:
        raise HTTPException(status_code=404, detail="execution record not found")
    return ExecutionRecordResponse(
        id=er.id,
        created_at=er.created_at,
        governance_proposal_id=er.governance_proposal_id,
        decision_record_id=er.decision_record_id,
        governance_decision_was_allow=er.governance_decision_was_allow,
        ok=er.ok,
        result=er.result,
    )


@app.post("/effective-policy/resolve", response_model=EffectivePolicyResponse)
def resolve_effective_policy_endpoint(req: EffectivePolicyResolveRequest) -> EffectivePolicyResponse:
    ephemeral = InternalProposal(
        proposal_id="effective-policy-resolve",
        action_type=InternalActionType.generic,
        action="noop",
        purpose="effective-policy",
        role=req.role,
        context=dict(req.context),
        parameters={},
    )
    ep = resolve_effective_policy_record(ephemeral)
    return EffectivePolicyResponse(
        autonomy_ceiling=ep.autonomy_ceiling.value,
        constitution_version=ep.constitution_version,
        sources=dict(ep.sources),
    )


@app.get("/proposals/{proposal_id}", response_model=ProposalRecordResponse)
def get_proposal(proposal_id: str) -> ProposalRecordResponse:
    rec = _proposals.get(proposal_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    return _governance_proposal_to_response(rec)


@app.post("/action/authorize", response_model=AuthorizeResponse)
def authorize(req: AuthorizeRequest) -> AuthorizeResponse:
    internal = _to_internal(req.proposal)
    gp, plan = evaluate_content(
        _proposals,
        internal,
        lambda p: build_execution_plan(p, _openshell),
    )
    gp_id = gp.id
    dr_id = _persist_decision(gp_id, internal.proposal_id, plan)
    audit_id = _audit.new_id()
    geo = GovernanceContext.from_proposal_context(dict(req.proposal.context))
    requested_by = geo.requested_by or parse_identity(internal.role)
    approved_by = geo.approved_by
    raw_refs = req.proposal.context.get("external_refs")
    external_refs = geo.external_refs if geo.external_refs else (raw_refs if isinstance(raw_refs, list) else [])
    generated_refs = generated_external_refs(internal, plan)
    governance_basis = [
        f"risk_tier={plan.risk_tier.value}",
        f"approval_policy.auto_allow={bool(plan.approval_policy.auto_allow) if plan.approval_policy else True}",
        f"approval_policy.approver_role={plan.approval_policy.approver_role if plan.approval_policy else 'operator'}",
    ]
    if geo.channel:
        governance_basis.append(f"channel={geo.channel}")
    rec = InternalAuditRecord(
        id=audit_id,
        created_at=_audit.now(),
        kind="authorize",
        proposal=internal,
        proposal_id=internal.proposal_id,
        action_type=internal.action_type,
        requested_by=requested_by,
        approved_by=approved_by,
        approval_status="pending" if plan.decision.value == "needs_approval" else "not_required",
        governance_basis=governance_basis,
        external_refs=list(external_refs) + generated_refs,
        decision=plan.decision,
        rationale=plan.rationale,
        plan=plan,
        result={},
        governance_proposal_id=gp_id,
        decision_record_id=dr_id,
    )
    _audit.put(rec)
    _link_proposal_audit(gp_id, audit_id)
    return AuthorizeResponse(decision=Decision(plan.decision.value), rationale=plan.rationale, audit_id=audit_id)


@app.post("/action/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest) -> SimulateResponse:
    internal = _to_internal(req.proposal)
    gp, plan = evaluate_content(
        _proposals,
        internal,
        lambda p: build_execution_plan(p, _openshell),
    )
    gp_id = gp.id
    dr_id = _persist_decision(gp_id, internal.proposal_id, plan)
    audit_id = _audit.new_id()
    geo = GovernanceContext.from_proposal_context(dict(req.proposal.context))
    requested_by = geo.requested_by or parse_identity(internal.role)
    approved_by = geo.approved_by
    raw_refs = req.proposal.context.get("external_refs")
    external_refs = geo.external_refs if geo.external_refs else (raw_refs if isinstance(raw_refs, list) else [])
    generated_refs = generated_external_refs(internal, plan)
    governance_basis = [
        f"risk_tier={plan.risk_tier.value}",
        f"approval_policy.auto_allow={bool(plan.approval_policy.auto_allow) if plan.approval_policy else True}",
        f"approval_policy.approver_role={plan.approval_policy.approver_role if plan.approval_policy else 'operator'}",
    ]
    if geo.channel:
        governance_basis.append(f"channel={geo.channel}")
    rec = InternalAuditRecord(
        id=audit_id,
        created_at=_audit.now(),
        kind="simulate",
        proposal=internal,
        proposal_id=internal.proposal_id,
        action_type=internal.action_type,
        requested_by=requested_by,
        approved_by=approved_by,
        approval_status="pending" if plan.decision.value == "needs_approval" else "not_required",
        governance_basis=governance_basis,
        external_refs=list(external_refs) + generated_refs,
        decision=plan.decision,
        rationale=plan.rationale,
        plan=plan,
        result={},
        governance_proposal_id=gp_id,
        decision_record_id=dr_id,
    )
    _audit.put(rec)
    _link_proposal_audit(gp_id, audit_id)
    simulation = _audit.to_public_payload(rec).get("plan", {})
    return SimulateResponse(audit_id=audit_id, simulation=simulation)


def _resolve_governance_proposal_for_approval(ref: str) -> Optional[GovernanceProposalRecord]:
    """
    Resolve a governance proposal for POST /approval-requests and for `steward_resume_proposal_id` on execute.

    Accepts (in order):
    1. Storage id (GovernanceProposalRecord.id) — returned as audit.governance_proposal_id / GET /proposals/{id}
    2. DecisionRecord.id — same audit often exposes decision_record_id; clients sometimes paste the wrong UUID
    3. Stable content proposal_id (64-hex SHA-256) — audit.payload.audit.proposal_id; distinct from storage id
    """
    key = (ref or "").strip()
    if not key:
        return None
    gp = _proposals.get(key)
    if gp is not None:
        return gp
    dr = _decisions.get(key)
    if dr is not None:
        return _proposals.get(dr.governance_proposal_id)
    matches = _proposals.find_by_content_proposal_id(key)
    if not matches:
        return None
    pending = [m for m in matches if m.state == ProposalLifecycleState.approval_pending]
    pool = pending if pending else matches
    return max(pool, key=lambda r: r.updated_at)


@app.post("/approval-requests", response_model=ApprovalRequestResponse)
def create_approval_request(req: CreateApprovalRequestBody) -> ApprovalRequestResponse:
    gp = _resolve_governance_proposal_for_approval(req.governance_proposal_id)
    if gp is None:
        raise HTTPException(status_code=404, detail="governance proposal not found")
    if gp.state != ProposalLifecycleState.approval_pending:
        raise HTTPException(status_code=400, detail="proposal is not pending approval")
    if not gp.decision_record_id:
        raise HTTPException(status_code=400, detail="proposal has no decision record")
    ar_id = _approvals.new_id()
    now = _approvals.now()
    initial_state = ApprovalRequestState.requested
    if req.expires_at is not None and req.expires_at <= now:
        initial_state = ApprovalRequestState.expired
    ar = ApprovalRequestRecord(
        id=ar_id,
        created_at=now,
        updated_at=now,
        state=initial_state,
        governance_proposal_id=gp.id,
        decision_record_id=gp.decision_record_id,
        expires_at=req.expires_at,
    )
    _approvals.put(ar)
    return ApprovalRequestResponse(
        id=ar.id,
        created_at=ar.created_at,
        updated_at=ar.updated_at,
        state=ar.state.value,
        governance_proposal_id=ar.governance_proposal_id,
        decision_record_id=ar.decision_record_id,
        expires_at=ar.expires_at,
    )


@app.get("/approval-requests/{ar_id}", response_model=ApprovalRequestResponse)
def get_approval_request(ar_id: str) -> ApprovalRequestResponse:
    ar = _approvals.get(ar_id)
    if ar is None:
        raise HTTPException(status_code=404, detail="approval request not found")
    return ApprovalRequestResponse(
        id=ar.id,
        created_at=ar.created_at,
        updated_at=ar.updated_at,
        state=ar.state.value,
        governance_proposal_id=ar.governance_proposal_id,
        decision_record_id=ar.decision_record_id,
        expires_at=ar.expires_at,
    )


@app.post("/approval-requests/{ar_id}/decision", response_model=ApprovalRequestResponse)
def decide_approval_request(ar_id: str, body: ApprovalDecisionBody) -> ApprovalRequestResponse:
    ar = _approvals.get(ar_id)
    if ar is None:
        raise HTTPException(status_code=404, detail="approval request not found")
    if ar.state == ApprovalRequestState.expired:
        raise HTTPException(status_code=400, detail="approval request has expired")
    if body.decision == "approved":
        ar.state = ApprovalRequestState.approved
    else:
        ar.state = ApprovalRequestState.rejected
        mark_proposal_denied_after_approval_rejection(_proposals, ar.governance_proposal_id)
    ar.decided_by = body.decided_by
    ar.updated_at = _approvals.now()
    _approvals.put(ar)
    return ApprovalRequestResponse(
        id=ar.id,
        created_at=ar.created_at,
        updated_at=ar.updated_at,
        state=ar.state.value,
        governance_proposal_id=ar.governance_proposal_id,
        decision_record_id=ar.decision_record_id,
        expires_at=ar.expires_at,
    )


@app.post("/action/execute", response_model=ExecuteResponse)
def execute(req: ExecuteRequest) -> ExecuteResponse:
    internal = _to_internal(req.proposal)
    ctx = dict(req.proposal.context)
    resumed = _maybe_resume_proposal(internal, ctx)
    if resumed:
        gp, plan = resumed
        gp_id = gp.id
        dr_id = gp.decision_record_id or _persist_decision(gp_id, internal.proposal_id, plan)
    else:
        gp, plan = evaluate_content(
            _proposals,
            internal,
            lambda p: build_execution_plan(p, _openshell),
        )
        gp_id = gp.id
        dr_id = _persist_decision(gp_id, internal.proposal_id, plan)

    plan_exec, used_approval = _effective_plan_for_execute(plan, gp_id, ctx)
    if used_approval:
        mark_proposal_approved_after_external_ok(_proposals, gp_id)
        # Prior decision record may still reflect needs_approval from authorize; snapshot effective allow for this execution.
        dr_id = _persist_decision(gp_id, internal.proposal_id, plan_exec)

    if plan_exec.decision == DomainDecision.allow:
        gpx = _proposals.get(gp_id)
        if gpx:
            mark_executing(_proposals, gpx)

    ok, result = execute_plan(_openshell, plan_exec)

    if plan_exec.decision == DomainDecision.allow:
        gpx = _proposals.get(gp_id)
        if gpx:
            mark_executed(_proposals, gpx, result, ok=ok)

    er_id = _persist_execution(
        gp_id,
        dr_id,
        plan_exec.decision == DomainDecision.allow,
        ok,
        result,
    )

    audit_id = _audit.new_id()
    geo = GovernanceContext.from_proposal_context(dict(req.proposal.context))
    requested_by = geo.requested_by or parse_identity(internal.role)
    approved_by = geo.approved_by
    raw_refs = req.proposal.context.get("external_refs")
    external_refs = geo.external_refs if geo.external_refs else (raw_refs if isinstance(raw_refs, list) else [])
    generated_refs = generated_external_refs(internal, plan_exec)
    governance_basis = [
        f"risk_tier={plan_exec.risk_tier.value}",
        f"approval_policy.auto_allow={bool(plan_exec.approval_policy.auto_allow) if plan_exec.approval_policy else True}",
        f"approval_policy.approver_role={plan_exec.approval_policy.approver_role if plan_exec.approval_policy else 'operator'}",
    ]
    if geo.channel:
        governance_basis.append(f"channel={geo.channel}")
    if plan_exec.decision != DomainDecision.allow:
        exec_approval_status: ApprovalStatus = (
            "pending" if plan_exec.decision == DomainDecision.needs_approval else "not_required"
        )
    elif ok:
        exec_approval_status = "approved"
    else:
        exec_approval_status = "rejected"
    rec = InternalAuditRecord(
        id=audit_id,
        created_at=_audit.now(),
        kind="execute",
        proposal=internal,
        proposal_id=internal.proposal_id,
        action_type=internal.action_type,
        requested_by=requested_by,
        approved_by=approved_by,
        approval_status=exec_approval_status,
        governance_basis=governance_basis,
        external_refs=list(external_refs) + generated_refs,
        decision=plan_exec.decision,
        rationale=plan_exec.rationale,
        plan=plan_exec,
        result=result,
        governance_proposal_id=gp_id,
        decision_record_id=dr_id,
        execution_record_id=er_id,
    )
    _audit.put(rec)
    _link_proposal_audit(gp_id, audit_id)

    if not ok:
        decision = plan_exec.decision.value
        rationale = plan_exec.rationale
        raise HTTPException(
            status_code=403,
            detail={
                "audit_id": audit_id,
                "decision": decision,
                "rationale": rationale,
                "result": result,
                "decision_record_id": dr_id,
                "execution_record_id": er_id,
                "user_hint": _execute_user_hint(
                    decision=decision,
                    rationale=rationale,
                    result=result,
                ),
            },
        )

    return ExecuteResponse(audit_id=audit_id, status="executed", result=result)

def _evaluate_candidates_impl(req: EvaluateCandidatesRequest) -> EvaluateCandidatesResponse:
    """
    Bulk-evaluate multiple candidate actions for one user request.
    Each candidate gets its own authorize-style audit record.
    """
    out: list[CandidateEvaluation] = []
    user_request_text: Optional[str] = None
    for c in req.candidates:
        ur = c.proposal.context.get("user_request")
        if isinstance(ur, str) and ur.strip():
            user_request_text = ur.strip()
            break

    all_candidates = [
        {
            "id": c.id,
            "label": c.label,
            "type": c.type,
            "action": c.proposal.action,
            "purpose": c.proposal.purpose,
        }
        for c in req.candidates
    ]
    for c in req.candidates:
        internal = _to_internal(c.proposal)
        plan = build_execution_plan(internal, _openshell)
        audit_id = _audit.new_id()

        geo = GovernanceContext.from_proposal_context(dict(c.proposal.context))
        requested_by = geo.requested_by or parse_identity(internal.role)
        approved_by = geo.approved_by
        raw_refs = c.proposal.context.get("external_refs")
        external_refs = geo.external_refs if geo.external_refs else (raw_refs if isinstance(raw_refs, list) else [])
        generated_refs = generated_external_refs(internal, plan)

        governance_basis = [
            f"risk_tier={plan.risk_tier.value}",
            f"approval_policy.auto_allow={bool(plan.approval_policy.auto_allow) if plan.approval_policy else True}",
            f"approval_policy.approver_role={plan.approval_policy.approver_role if plan.approval_policy else 'operator'}",
            "bulk_evaluate=true",
        ]
        if geo.channel:
            governance_basis.append(f"channel={geo.channel}")

        rec = InternalAuditRecord(
            id=audit_id,
            created_at=_audit.now(),
            kind="authorize",
            proposal=internal,
            proposal_id=internal.proposal_id,
            action_type=internal.action_type,
            requested_by=requested_by,
            approved_by=approved_by,
            approval_status="pending" if plan.decision.value == "needs_approval" else "not_required",
            governance_basis=governance_basis,
            external_refs=list(external_refs) + generated_refs,
            decision=plan.decision,
            rationale=plan.rationale,
            plan=plan,
            result={
                "candidate": {"id": c.id, "label": c.label},
                "user_request": user_request_text,
                "candidates": all_candidates,
                "evaluation": {
                    "decision": plan.decision.value,
                    "rationale": plan.rationale,
                    "risk_tier": plan.risk_tier.value,
                },
            },
        )
        _audit.put(rec)
        out.append(
            CandidateEvaluation(
                id=c.id,
                label=c.label,
                decision=Decision(plan.decision.value),
                rationale=plan.rationale,
                audit_id=audit_id,
                risk_tier=plan.risk_tier.value,
            )
        )

    def risk_rank(rt: str) -> int:
        return {"low": 0, "medium": 1, "high": 2}.get(rt, 3)

    def type_rank(t: Optional[str]) -> int:
        # Lower is better (more goal-advancing).
        return {"remediation": 0, "administrative": 1, "diagnostic": 2}.get((t or "").strip().lower(), 3)

    def goal_rank(e: CandidateEvaluation) -> int:
        # Npm-install scenario: prefer the targeted remediation when relevant.
        # (This remains intentionally narrow-scope.)
        ur = (user_request_text or "").lower()
        if "npm" in ur and ("install" in ur or "installs" in ur):
            if e.id == "approve-npm-registry":
                return 0
            if e.id == "get-draft":
                return 1
        if ("git" in ur and "clone" in ur) or ("git clone" in ur):
            if e.id in {"approve-github", "approve-raw-githubusercontent"}:
                return 0
            if e.id == "get-draft":
                return 1
        return 2

    def candidate_type_for(e: CandidateEvaluation) -> Optional[str]:
        for c in req.candidates:
            if c.id == e.id:
                return c.type
        return None

    # Selection rule (goal-aware):
    # - Prefer the lowest-risk candidate that best advances the user goal.
    # - Diagnostic actions win only when remediation/admin actions are unavailable (not allowed / not needs_approval).
    allowed = [e for e in out if e.decision == Decision.allow]
    needs = [e for e in out if e.decision == Decision.needs_approval]
    selected = None
    rule = "goal_aware_lowest_risk_allowed"
    rationale = "Selected the lowest-risk allowed candidate that best advances the request."
    if allowed:
        selected = sorted(
            allowed,
            key=lambda e: (
                goal_rank(e),
                type_rank(candidate_type_for(e)),
                risk_rank(e.risk_tier),
                e.id,
            ),
        )[0]
    elif needs:
        rule = "goal_aware_lowest_risk_needs_approval"
        rationale = "No candidate was allowed; selected the lowest-risk candidate that best advances the request but requires approval."
        selected = sorted(
            needs,
            key=lambda e: (
                goal_rank(e),
                type_rank(candidate_type_for(e)),
                risk_rank(e.risk_tier),
                e.id,
            ),
        )[0]
    else:
        rule = "none"
        rationale = "No candidate was allowed or eligible for approval."

    selection = CandidateSelection(
        selected_id=selected.id if selected else None,
        selected_label=selected.label if selected else None,
        decision=selected.decision if selected else None,
        rationale=rationale,
        rule=rule,
    )

    return EvaluateCandidatesResponse(evaluations=out, selection=selection)


@app.post("/action/evaluate", response_model=EvaluateCandidatesResponse)
def evaluate(req: EvaluateCandidatesRequest) -> EvaluateCandidatesResponse:
    return _evaluate_candidates_impl(req)


@app.post("/candidate-sets/evaluate", response_model=CandidateSetEvaluateResponse)
def candidate_sets_evaluate(req: EvaluateCandidatesRequest) -> CandidateSetEvaluateResponse:
    res = _evaluate_candidates_impl(req)
    sid = _candidate_sets.new_id()
    now = _candidate_sets.now()
    summary = [
        {
            "id": e.id,
            "label": e.label,
            "decision": e.decision.value,
            "rationale": e.rationale,
            "risk_tier": e.risk_tier,
            "audit_id": e.audit_id,
        }
        for e in res.evaluations
    ]
    rec = CandidateActionSetRecord(
        id=sid,
        created_at=now,
        updated_at=now,
        request_summary={
            "candidate_count": len(req.candidates),
            "candidate_ids": [c.id for c in req.candidates],
        },
        candidate_ids=[c.id for c in req.candidates],
        evaluations_summary=summary,
        selected_id=res.selection.selected_id,
        selected_label=res.selection.selected_label,
        selection_rationale=res.selection.rationale,
        selection_rule=res.selection.rule,
    )
    _candidate_sets.put(rec)
    return CandidateSetEvaluateResponse(
        candidate_set_id=sid,
        evaluations=res.evaluations,
        selection=res.selection,
    )


@app.get("/candidate-sets/{set_id}", response_model=CandidateSetRecordResponse)
def get_candidate_set(set_id: str) -> CandidateSetRecordResponse:
    rec = _candidate_sets.get(set_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="candidate set not found")
    return CandidateSetRecordResponse(
        id=rec.id,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        request_summary=dict(rec.request_summary),
        candidate_ids=list(rec.candidate_ids),
        evaluations_summary=list(rec.evaluations_summary),
        selected_id=rec.selected_id,
        selected_label=rec.selected_label,
        selection_rationale=rec.selection_rationale,
        selection_rule=rec.selection_rule,
    )


@app.get("/capabilities/{cap_id}", response_model=CapabilityDefinitionResponse)
def get_capability_definition(cap_id: str) -> CapabilityDefinitionResponse:
    c = CAPABILITIES.get(cap_id)
    if c is None:
        raise HTTPException(status_code=404, detail="capability not found")
    return CapabilityDefinitionResponse(
        id=c.id,
        resource_family=c.resource_family,
        risk_tier_default=c.risk_tier_default.value,
        description=c.description,
        version=c.version,
    )


@app.get("/tools/{tool_id}", response_model=ToolDefinitionResponse)
def get_tool_definition(tool_id: str) -> ToolDefinitionResponse:
    t = TOOLS.get(tool_id)
    if t is None:
        raise HTTPException(status_code=404, detail="tool not found")
    return ToolDefinitionResponse(
        id=t.id,
        steward_action_pattern=t.steward_action_pattern,
        description=t.description,
    )


@app.get("/roles/{role_id}", response_model=RoleDefinitionResponse)
def get_role_definition(role_id: str) -> RoleDefinitionResponse:
    r = ROLES.get(role_id.strip().lower())
    if r is None:
        raise HTTPException(status_code=404, detail="role not found")
    return RoleDefinitionResponse(
        id=r.id,
        display_name=r.display_name,
        description=r.description,
        version=r.version,
    )


@app.get("/policies/{policy_id}", response_model=PolicyDefinitionResponse)
def get_policy_definition(policy_id: str) -> PolicyDefinitionResponse:
    p = POLICIES.get(policy_id)
    if p is None:
        raise HTTPException(status_code=404, detail="policy not found")
    return PolicyDefinitionResponse(
        id=p.id,
        display_name=p.display_name,
        description=p.description,
        version=p.version,
    )


@app.get("/effective-policy", response_model=EffectivePolicyResponse)
def get_effective_policy_query(role: Optional[str] = None) -> EffectivePolicyResponse:
    return resolve_effective_policy_endpoint(EffectivePolicyResolveRequest(role=role, context={}))


@app.get("/audit/{id}", response_model=AuditRecord)
def get_audit(id: str) -> AuditRecord:
    internal = _audit.get(id)
    if internal is None:
        raise HTTPException(status_code=404, detail="audit record not found")
    return _to_public_audit(internal)
