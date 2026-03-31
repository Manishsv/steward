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


@app.post("/action/authorize", response_model=AuthorizeResponse)
def authorize(req: AuthorizeRequest) -> AuthorizeResponse:
    internal = _to_internal(req.proposal)
    plan = build_execution_plan(internal, _openshell)
    audit_id = _audit.new_id()
    requested_by = parse_identity(req.proposal.context.get("requested_by") or internal.role)
    approved_by = parse_identity(req.proposal.context.get("approved_by"))
    external_refs = req.proposal.context.get("external_refs")
    generated_refs = generated_external_refs(internal, plan)
    governance_basis = [
        f"risk_tier={plan.risk_tier.value}",
        f"approval_policy.auto_allow={bool(plan.approval_policy.auto_allow) if plan.approval_policy else True}",
        f"approval_policy.approver_role={plan.approval_policy.approver_role if plan.approval_policy else 'operator'}",
    ]
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
        external_refs=(external_refs if isinstance(external_refs, list) else []) + generated_refs,
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
    requested_by = parse_identity(req.proposal.context.get("requested_by") or internal.role)
    approved_by = parse_identity(req.proposal.context.get("approved_by"))
    external_refs = req.proposal.context.get("external_refs")
    generated_refs = generated_external_refs(internal, plan)
    governance_basis = [
        f"risk_tier={plan.risk_tier.value}",
        f"approval_policy.auto_allow={bool(plan.approval_policy.auto_allow) if plan.approval_policy else True}",
        f"approval_policy.approver_role={plan.approval_policy.approver_role if plan.approval_policy else 'operator'}",
    ]
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
        external_refs=(external_refs if isinstance(external_refs, list) else []) + generated_refs,
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
    requested_by = parse_identity(req.proposal.context.get("requested_by") or internal.role)
    approved_by = parse_identity(req.proposal.context.get("approved_by"))
    external_refs = req.proposal.context.get("external_refs")
    generated_refs = generated_external_refs(internal, plan)
    governance_basis = [
        f"risk_tier={plan.risk_tier.value}",
        f"approval_policy.auto_allow={bool(plan.approval_policy.auto_allow) if plan.approval_policy else True}",
        f"approval_policy.approver_role={plan.approval_policy.approver_role if plan.approval_policy else 'operator'}",
    ]
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
        external_refs=(external_refs if isinstance(external_refs, list) else []) + generated_refs,
        decision=plan.decision,
        rationale=plan.rationale,
        plan=plan,
        result=result,
    )
    _audit.put(rec)

    if not ok:
        raise HTTPException(
            status_code=403,
            detail={"audit_id": audit_id, "decision": plan.decision.value, "rationale": plan.rationale},
        )

    return ExecuteResponse(audit_id=audit_id, status="executed", result=result)


@app.get("/audit/{id}", response_model=AuditRecord)
def get_audit(id: str) -> AuditRecord:
    internal = _audit.get(id)
    if internal is None:
        raise HTTPException(status_code=404, detail="audit record not found")
    return _to_public_audit(internal)
