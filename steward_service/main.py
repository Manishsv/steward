from __future__ import annotations

from datetime import datetime
from enum import Enum
import hashlib
from typing import Any, Dict, Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .audit_store import InMemoryAuditStore
from .canonical import canonical_json_bytes
from .domain import AuditRecord as InternalAuditRecord
from .domain import ActionType as InternalActionType
from .domain import Proposal as InternalProposal
from .identity import parse_identity
from .governance import build_execution_plan, execute_plan, generated_external_refs
from .governance_context import GovernanceContext
from .openshell_client import create_openshell_client


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


_audit = InMemoryAuditStore()
_openshell = create_openshell_client()


def _stable_proposal_id(p: ActionProposal) -> str:
    payload = {
        "action": p.action,
        "purpose": p.purpose,
        "role": p.role,
        "context": p.context,
        "parameters": p.parameters,
    }
    raw = canonical_json_bytes(payload)
    return hashlib.sha256(raw).hexdigest()


def _action_type(action: str) -> InternalActionType:
    a = action.strip().lower()
    if a.startswith("openshell.draft_policy."):
        return InternalActionType.openshell_draft_policy
    return InternalActionType.generic


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


@app.post("/action/authorize", response_model=AuthorizeResponse)
def authorize(req: AuthorizeRequest) -> AuthorizeResponse:
    internal = _to_internal(req.proposal)
    plan = build_execution_plan(internal, _openshell)
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
    )
    _audit.put(rec)
    return AuthorizeResponse(decision=Decision(plan.decision.value), rationale=plan.rationale, audit_id=audit_id)


@app.post("/action/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest) -> SimulateResponse:
    internal = _to_internal(req.proposal)
    plan = build_execution_plan(internal, _openshell)
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
    )
    _audit.put(rec)
    simulation = _audit.to_public_payload(rec).get("plan", {})
    return SimulateResponse(audit_id=audit_id, simulation=simulation)


@app.post("/action/execute", response_model=ExecuteResponse)
def execute(req: ExecuteRequest) -> ExecuteResponse:
    internal = _to_internal(req.proposal)
    plan = build_execution_plan(internal, _openshell)
    ok, result = execute_plan(_openshell, plan)

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
        kind="execute",
        proposal=internal,
        proposal_id=internal.proposal_id,
        action_type=internal.action_type,
        requested_by=requested_by,
        approved_by=approved_by,
        approval_status="approved" if ok else "rejected",
        governance_basis=governance_basis,
        external_refs=list(external_refs) + generated_refs,
        decision=plan.decision,
        rationale=plan.rationale,
        plan=plan,
        result=result,
    )
    _audit.put(rec)

    if not ok:
        decision = plan.decision.value
        rationale = plan.rationale
        raise HTTPException(
            status_code=403,
            detail={
                "audit_id": audit_id,
                "decision": decision,
                "rationale": rationale,
                "result": result,
                "user_hint": _execute_user_hint(
                    decision=decision,
                    rationale=rationale,
                    result=result,
                ),
            },
        )

    return ExecuteResponse(audit_id=audit_id, status="executed", result=result)

@app.post("/action/evaluate", response_model=EvaluateCandidatesResponse)
def evaluate(req: EvaluateCandidatesRequest) -> EvaluateCandidatesResponse:
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


@app.get("/audit/{id}", response_model=AuditRecord)
def get_audit(id: str) -> AuditRecord:
    internal = _audit.get(id)
    if internal is None:
        raise HTTPException(status_code=404, detail="audit record not found")
    return _to_public_audit(internal)
