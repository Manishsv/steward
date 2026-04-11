"""JSON-safe encode/decode for persisted domain records."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..domain import (
    ActionType,
    ApprovalPolicy,
    ApprovalRequestRecord,
    ApprovalRequestState,
    ApprovalRequirement,
    AuditRecord,
    AuthorizationDecision,
    ApprovalState,
    CandidateActionSetRecord,
    Decision,
    DecisionRecord,
    ExecutionPlan,
    ExecutionRecord,
    ExecutionStep,
    GovernanceProposalRecord,
    InstitutionalDecisionRecord,
    Proposal,
    ProposalLifecycleState,
    RiskTier,
)
from ..identity import Identity


def _dt_encode(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _dt_decode(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def identity_to_dict(i: Optional[Identity]) -> Optional[Dict[str, str]]:
    if i is None:
        return None
    return {"kind": i.kind, "value": i.value}


def identity_from_dict(d: Optional[Dict[str, Any]]) -> Optional[Identity]:
    if not d:
        return None
    return Identity(kind=str(d.get("kind", "unknown")), value=str(d.get("value", "")))


def proposal_to_dict(p: Proposal) -> Dict[str, Any]:
    return {
        "proposal_id": p.proposal_id,
        "action_type": p.action_type.value,
        "action": p.action,
        "purpose": p.purpose,
        "role": p.role,
        "context": dict(p.context),
        "parameters": dict(p.parameters),
    }


def proposal_from_dict(d: Dict[str, Any]) -> Proposal:
    return Proposal(
        proposal_id=d["proposal_id"],
        action_type=ActionType(d["action_type"]),
        action=d["action"],
        purpose=d["purpose"],
        role=d.get("role"),
        context=dict(d.get("context") or {}),
        parameters=dict(d.get("parameters") or {}),
    )


def execution_plan_to_dict(plan: Optional[ExecutionPlan]) -> Optional[Dict[str, Any]]:
    if plan is None:
        return None
    return {
        "decision": plan.decision.value,
        "authorization_decision": plan.authorization_decision.value,
        "approval_state": plan.approval_state.value,
        "rationale": plan.rationale,
        "risk_tier": plan.risk_tier.value,
        "approval_policy": asdict(plan.approval_policy) if plan.approval_policy else None,
        "requirements": [asdict(r) for r in plan.requirements],
        "steps": [asdict(s) for s in plan.steps],
        "capability_id": plan.capability_id,
        "tool_id": plan.tool_id,
    }


def execution_plan_from_dict(d: Optional[Dict[str, Any]]) -> Optional[ExecutionPlan]:
    if not d:
        return None
    reqs: List[ApprovalRequirement] = []
    for r in d.get("requirements") or []:
        reqs.append(
            ApprovalRequirement(
                requirement=r["requirement"],
                reason=r["reason"],
                details=dict(r.get("details") or {}),
            )
        )
    steps: List[ExecutionStep] = []
    for s in d.get("steps") or []:
        steps.append(
            ExecutionStep(
                step=int(s["step"]),
                type=s["type"],
                description=s["description"],
                payload=dict(s.get("payload") or {}),
            )
        )
    ap_raw = d.get("approval_policy")
    ap: Optional[ApprovalPolicy] = None
    if ap_raw:
        ap = ApprovalPolicy(
            approver_role=ap_raw["approver_role"],
            auto_allow=bool(ap_raw["auto_allow"]),
            notes=str(ap_raw.get("notes") or ""),
        )
    return ExecutionPlan(
        decision=Decision(d["decision"]),
        authorization_decision=AuthorizationDecision(d["authorization_decision"]),
        approval_state=ApprovalState(d["approval_state"]),
        rationale=d["rationale"],
        risk_tier=RiskTier(d.get("risk_tier", "low")),
        approval_policy=ap,
        requirements=reqs,
        steps=steps,
        capability_id=str(d.get("capability_id") or ""),
        tool_id=str(d.get("tool_id") or ""),
    )


def audit_record_to_dict(r: AuditRecord) -> Dict[str, Any]:
    return {
        "id": r.id,
        "created_at": _dt_encode(r.created_at),
        "kind": r.kind,
        "proposal": proposal_to_dict(r.proposal),
        "proposal_id": r.proposal_id,
        "action_type": r.action_type.value,
        "requested_by": identity_to_dict(r.requested_by),
        "approved_by": identity_to_dict(r.approved_by),
        "approval_status": r.approval_status,
        "governance_basis": list(r.governance_basis),
        "external_refs": list(r.external_refs),
        "decision": r.decision.value if r.decision else None,
        "rationale": r.rationale,
        "plan": execution_plan_to_dict(r.plan),
        "result": dict(r.result),
        "governance_proposal_id": r.governance_proposal_id,
        "decision_record_id": r.decision_record_id,
        "execution_record_id": r.execution_record_id,
    }


def audit_record_from_dict(d: Dict[str, Any]) -> AuditRecord:
    dec = d.get("decision")
    return AuditRecord(
        id=d["id"],
        created_at=_dt_decode(d["created_at"]),
        kind=d["kind"],
        proposal=proposal_from_dict(d["proposal"]),
        proposal_id=d["proposal_id"],
        action_type=ActionType(d["action_type"]),
        requested_by=identity_from_dict(d.get("requested_by")),
        approved_by=identity_from_dict(d.get("approved_by")),
        approval_status=d.get("approval_status", "not_required"),
        governance_basis=list(d.get("governance_basis") or []),
        external_refs=list(d.get("external_refs") or []),
        decision=Decision(dec) if dec else None,
        rationale=d.get("rationale"),
        plan=execution_plan_from_dict(d.get("plan")),
        result=dict(d.get("result") or {}),
        governance_proposal_id=d.get("governance_proposal_id"),
        decision_record_id=d.get("decision_record_id"),
        execution_record_id=d.get("execution_record_id"),
    )


def governance_proposal_to_dict(r: GovernanceProposalRecord) -> Dict[str, Any]:
    gd = r.governance_decision.value if r.governance_decision else None
    return {
        "id": r.id,
        "created_at": _dt_encode(r.created_at),
        "updated_at": _dt_encode(r.updated_at),
        "state": r.state.value,
        "proposal": proposal_to_dict(r.proposal),
        "plan": execution_plan_to_dict(r.plan),
        "governance_decision": gd,
        "governance_rationale": r.governance_rationale,
        "linked_audit_ids": list(r.linked_audit_ids),
        "execution_result": dict(r.execution_result),
        "decision_record_id": r.decision_record_id,
        "execution_record_id": r.execution_record_id,
    }


def governance_proposal_from_dict(d: Dict[str, Any]) -> GovernanceProposalRecord:
    gd_raw = d.get("governance_decision")
    return GovernanceProposalRecord(
        id=d["id"],
        created_at=_dt_decode(d["created_at"]),
        updated_at=_dt_decode(d["updated_at"]),
        state=ProposalLifecycleState(d["state"]),
        proposal=proposal_from_dict(d["proposal"]),
        plan=execution_plan_from_dict(d.get("plan")),
        governance_decision=Decision(gd_raw) if gd_raw else None,
        governance_rationale=d.get("governance_rationale"),
        linked_audit_ids=list(d.get("linked_audit_ids") or []),
        execution_result=dict(d.get("execution_result") or {}),
        decision_record_id=d.get("decision_record_id"),
        execution_record_id=d.get("execution_record_id"),
    )


def decision_record_to_dict(r: DecisionRecord) -> Dict[str, Any]:
    return {
        "id": r.id,
        "created_at": _dt_encode(r.created_at),
        "governance_proposal_id": r.governance_proposal_id,
        "content_proposal_id": r.content_proposal_id,
        "decision": r.decision.value,
        "rationale": r.rationale,
        "plan_snapshot": dict(r.plan_snapshot),
    }


def decision_record_from_dict(d: Dict[str, Any]) -> DecisionRecord:
    return DecisionRecord(
        id=d["id"],
        created_at=_dt_decode(d["created_at"]),
        governance_proposal_id=d["governance_proposal_id"],
        content_proposal_id=d["content_proposal_id"],
        decision=Decision(d["decision"]),
        rationale=d["rationale"],
        plan_snapshot=dict(d.get("plan_snapshot") or {}),
    )


def execution_record_to_dict(r: ExecutionRecord) -> Dict[str, Any]:
    return {
        "id": r.id,
        "created_at": _dt_encode(r.created_at),
        "governance_proposal_id": r.governance_proposal_id,
        "decision_record_id": r.decision_record_id,
        "governance_decision_was_allow": r.governance_decision_was_allow,
        "ok": r.ok,
        "result": dict(r.result),
    }


def execution_record_from_dict(d: Dict[str, Any]) -> ExecutionRecord:
    return ExecutionRecord(
        id=d["id"],
        created_at=_dt_decode(d["created_at"]),
        governance_proposal_id=d["governance_proposal_id"],
        decision_record_id=d["decision_record_id"],
        governance_decision_was_allow=bool(d["governance_decision_was_allow"]),
        ok=bool(d["ok"]),
        result=dict(d.get("result") or {}),
    )


def approval_request_to_dict(r: ApprovalRequestRecord) -> Dict[str, Any]:
    return {
        "id": r.id,
        "created_at": _dt_encode(r.created_at),
        "updated_at": _dt_encode(r.updated_at),
        "state": r.state.value,
        "governance_proposal_id": r.governance_proposal_id,
        "decision_record_id": r.decision_record_id,
        "decided_by": r.decided_by,
        "notes": r.notes,
        "expires_at": _dt_encode(r.expires_at) if r.expires_at else None,
    }


def approval_request_from_dict(d: Dict[str, Any]) -> ApprovalRequestRecord:
    exp = d.get("expires_at")
    return ApprovalRequestRecord(
        id=d["id"],
        created_at=_dt_decode(d["created_at"]),
        updated_at=_dt_decode(d["updated_at"]),
        state=ApprovalRequestState(d["state"]),
        governance_proposal_id=d["governance_proposal_id"],
        decision_record_id=d["decision_record_id"],
        decided_by=d.get("decided_by"),
        notes=str(d.get("notes") or ""),
        expires_at=_dt_decode(exp) if exp else None,
    )


def candidate_set_to_dict(r: CandidateActionSetRecord) -> Dict[str, Any]:
    return {
        "id": r.id,
        "created_at": _dt_encode(r.created_at),
        "updated_at": _dt_encode(r.updated_at),
        "request_summary": dict(r.request_summary),
        "candidate_ids": list(r.candidate_ids),
        "evaluations_summary": list(r.evaluations_summary),
        "selected_id": r.selected_id,
        "selected_label": r.selected_label,
        "selection_rationale": r.selection_rationale,
        "selection_rule": r.selection_rule,
    }


def candidate_set_from_dict(d: Dict[str, Any]) -> CandidateActionSetRecord:
    return CandidateActionSetRecord(
        id=d["id"],
        created_at=_dt_decode(d["created_at"]),
        updated_at=_dt_decode(d["updated_at"]),
        request_summary=dict(d.get("request_summary") or {}),
        candidate_ids=list(d.get("candidate_ids") or []),
        evaluations_summary=list(d.get("evaluations_summary") or []),
        selected_id=d.get("selected_id"),
        selected_label=d.get("selected_label"),
        selection_rationale=d["selection_rationale"],
        selection_rule=d["selection_rule"],
    )


def institution_record_to_dict(r: InstitutionalDecisionRecord) -> Dict[str, Any]:
    return {
        "id": r.id,
        "created_at": _dt_encode(r.created_at),
        "proposal": proposal_to_dict(r.proposal),
        "outcome": r.outcome,
        "rationale": r.rationale,
        "domain": r.domain,
        "rule_id": r.rule_id,
        "missing_facts": list(r.missing_facts),
    }


def institution_record_from_dict(d: Dict[str, Any]) -> InstitutionalDecisionRecord:
    return InstitutionalDecisionRecord(
        id=d["id"],
        created_at=_dt_decode(d["created_at"]),
        proposal=proposal_from_dict(d["proposal"]),
        outcome=d["outcome"],
        rationale=d["rationale"],
        domain=d.get("domain", "institution.expenditure.v1"),
        rule_id=str(d.get("rule_id") or ""),
        missing_facts=list(d.get("missing_facts") or []),
    )
