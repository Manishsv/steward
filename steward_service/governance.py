from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import grpc

from .domain import (
    ActionType,
    ApprovalPolicy,
    ApprovalRequirement,
    ApprovalState,
    AuthorizationDecision,
    Decision,
    ExecutionPlan,
    ExecutionStep,
    Proposal,
    RiskTier,
)
from .capability_registry import (
    capability_and_tool_for_action,
    merge_action_and_capability_risk,
)
from .effective_policy import resolve_effective_policy, risk_exceeds_autonomy_ceiling
from .openshell_client import DraftPolicyChunk, OpenShellClient


class StewardActions:
    # Phase 1A: draft policy governance
    DRAFT_GET = "openshell.draft_policy.get"
    DRAFT_APPROVE = "openshell.draft_policy.approve"
    DRAFT_REJECT = "openshell.draft_policy.reject"
    DRAFT_EDIT = "openshell.draft_policy.edit"
    DRAFT_APPROVE_ALL = "openshell.draft_policy.approve_all"
    DRAFT_CLEAR = "openshell.draft_policy.clear"
    # Phase 2: candidate actions (still draft-policy scoped)
    DRAFT_APPROVE_MATCHING = "openshell.draft_policy.approve_matching"


_RISK_TIER_BY_ACTION: Dict[str, RiskTier] = {
    StewardActions.DRAFT_GET: RiskTier.low,
    StewardActions.DRAFT_APPROVE: RiskTier.medium,
    StewardActions.DRAFT_REJECT: RiskTier.medium,
    StewardActions.DRAFT_EDIT: RiskTier.medium,
    StewardActions.DRAFT_APPROVE_ALL: RiskTier.high,
    StewardActions.DRAFT_CLEAR: RiskTier.high,
    StewardActions.DRAFT_APPROVE_MATCHING: RiskTier.medium,
}


_APPROVER_ROLE_BY_ACTION: Dict[str, str] = {
    StewardActions.DRAFT_GET: "operator",
    StewardActions.DRAFT_APPROVE: "operator",
    StewardActions.DRAFT_REJECT: "operator",
    StewardActions.DRAFT_EDIT: "operator",
    StewardActions.DRAFT_APPROVE_ALL: "operator",
    StewardActions.DRAFT_CLEAR: "operator",
    StewardActions.DRAFT_APPROVE_MATCHING: "operator",
}


def _approval_requirements_for_chunk(chunk: DraftPolicyChunk) -> List[ApprovalRequirement]:
    reqs: List[ApprovalRequirement] = []
    if chunk.security_notes:
        reqs.append(
            ApprovalRequirement(
                requirement="security_review",
                reason="Chunk has security_notes from analysis.",
                details={"chunk_id": chunk.id, "security_notes": chunk.security_notes},
            )
        )
    return reqs


def _require_operator(proposal: Proposal, *, reason: str) -> List[ApprovalRequirement]:
    role = (proposal.role or "").strip().lower()
    if role == "operator":
        return []
    return [
        ApprovalRequirement(
            requirement="operator",
            reason=reason,
            details={"role": proposal.role},
        )
    ]


def build_execution_plan(
    proposal: Proposal, openshell: OpenShellClient
) -> ExecutionPlan:
    action = proposal.action.strip()
    cap_id, tool_id = capability_and_tool_for_action(action)
    purpose = proposal.purpose.strip()
    if not action or not purpose:
        return ExecutionPlan(
            decision=Decision.deny,
            authorization_decision=AuthorizationDecision.deny,
            approval_state=ApprovalState.not_required,
            rationale="Missing action or purpose.",
            requirements=[],
            steps=[],
            capability_id=cap_id,
            tool_id=tool_id,
        )

    # Deny-by-default: if we have no governance policy for an action, do not allow.
    if action not in {
        StewardActions.DRAFT_GET,
        StewardActions.DRAFT_APPROVE,
        StewardActions.DRAFT_REJECT,
        StewardActions.DRAFT_EDIT,
        StewardActions.DRAFT_APPROVE_ALL,
        StewardActions.DRAFT_CLEAR,
        StewardActions.DRAFT_APPROVE_MATCHING,
    }:
        family = action.split(".", 1)[0] if "." in action else action
        return ExecutionPlan(
            decision=Decision.deny,
            authorization_decision=AuthorizationDecision.deny,
            approval_state=ApprovalState.not_required,
            rationale=(
                "Unsupported action: no governance policy exists for this action. "
                f"(family={family})"
            ),
            risk_tier=RiskTier.high,
            approval_policy=ApprovalPolicy(
                approver_role="operator",
                auto_allow=False,
                notes="deny_by_default",
            ),
            requirements=[
                ApprovalRequirement(
                    requirement="operator",
                    reason="Unsupported action requires explicit policy to be added before execution.",
                    details={"action": action},
                )
            ],
            steps=[],
            capability_id=cap_id,
            tool_id=tool_id,
        )

    risk_tier = merge_action_and_capability_risk(
        _RISK_TIER_BY_ACTION.get(action, RiskTier.medium),
        cap_id,
    )
    effective = resolve_effective_policy(proposal)
    approval_policy = ApprovalPolicy(
        approver_role=_APPROVER_ROLE_BY_ACTION.get(action, "operator"),  # type: ignore[arg-type]
        auto_allow=not risk_exceeds_autonomy_ceiling(risk_tier, effective.autonomy_ceiling),
        notes=f"phase_1a_risk={risk_tier.value};effective_ceiling={effective.autonomy_ceiling.value}",
    )

    sandbox_name = str(proposal.parameters.get("sandbox_name", "")).strip()
    if not sandbox_name:
        return ExecutionPlan(
            decision=Decision.deny,
            authorization_decision=AuthorizationDecision.deny,
            approval_state=ApprovalState.not_required,
            rationale="Missing parameters.sandbox_name.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=[],
            capability_id=cap_id,
            tool_id=tool_id,
        )

    trusted = proposal.context.get("steward_identity_trusted")
    if trusted is False:
        return ExecutionPlan(
            decision=Decision.deny,
            authorization_decision=AuthorizationDecision.deny,
            approval_state=ApprovalState.not_required,
            rationale="Untrusted identity context (steward_identity_trusted=false).",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=[],
            capability_id=cap_id,
            tool_id=tool_id,
        )

    outcome_hint = str(proposal.context.get("steward_governance_outcome_hint", "")).strip().lower()
    if outcome_hint == "escalate":
        return ExecutionPlan(
            decision=Decision.deny,
            authorization_decision=AuthorizationDecision.deny,
            approval_state=ApprovalState.not_required,
            rationale="Governance outcome: escalate.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=[],
            capability_id=cap_id,
            tool_id=tool_id,
        )
    if outcome_hint == "defer":
        return ExecutionPlan(
            decision=Decision.deny,
            authorization_decision=AuthorizationDecision.deny,
            approval_state=ApprovalState.not_required,
            rationale="Governance outcome: defer.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=[],
            capability_id=cap_id,
            tool_id=tool_id,
        )
    if outcome_hint == "simulate_only":
        return ExecutionPlan(
            decision=Decision.needs_approval,
            authorization_decision=AuthorizationDecision.allow,
            approval_state=ApprovalState.pending,
            rationale="Governance outcome: simulate_only (execution gated).",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[
                ApprovalRequirement(
                    requirement="operator",
                    reason="simulate_only hint requires explicit approval to execute.",
                    details={"hint": outcome_hint},
                )
            ],
            steps=[],
            capability_id=cap_id,
            tool_id=tool_id,
        )

    steps: List[ExecutionStep] = []
    requirements: List[ApprovalRequirement] = []

    if action == StewardActions.DRAFT_GET:
        steps.append(
            ExecutionStep(
                step=1,
                type="openshell.get_draft_policy",
                description="Fetch draft policy chunks for sandbox.",
                payload={
                    "sandbox_name": sandbox_name,
                    "status_filter": proposal.parameters.get("status_filter", ""),
                },
            )
        )
        return ExecutionPlan(
            decision=Decision.allow,
            authorization_decision=AuthorizationDecision.allow,
            approval_state=ApprovalState.not_required,
            rationale="Read-only draft policy fetch.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=steps,
            capability_id=cap_id,
            tool_id=tool_id,
        )

    # Mutations require operator role (approver_role concept)
    requirements.extend(_require_operator(proposal, reason="Draft policy mutations require operator role."))

    skill = str(proposal.context.get("steward_skill_profile", "")).strip().lower()
    if skill == "review_required":
        requirements.append(
            ApprovalRequirement(
                requirement="operator",
                reason="Skill profile requires human review.",
                details={"steward_skill_profile": skill},
            )
        )
    if outcome_hint == "recommend":
        requirements.append(
            ApprovalRequirement(
                requirement="operator",
                reason="Governance outcome: recommend (human confirmation).",
                details={"hint": outcome_hint},
            )
        )

    chunk_id = str(proposal.parameters.get("chunk_id", "")).strip()

    if action in {StewardActions.DRAFT_APPROVE, StewardActions.DRAFT_REJECT, StewardActions.DRAFT_EDIT}:
        if not chunk_id:
            return ExecutionPlan(
                decision=Decision.deny,
                authorization_decision=AuthorizationDecision.deny,
                approval_state=ApprovalState.not_required,
                rationale="Missing parameters.chunk_id.",
                risk_tier=risk_tier,
                approval_policy=approval_policy,
                requirements=[],
                steps=[],
                capability_id=cap_id,
                tool_id=tool_id,
            )
        chunk = _find_chunk(openshell, sandbox_name=sandbox_name, chunk_id=chunk_id)
        if chunk is not None:
            requirements.extend(_approval_requirements_for_chunk(chunk))

    # EffectivePolicy: tiers above the autonomy ceiling require explicit approval.
    if risk_exceeds_autonomy_ceiling(risk_tier, effective.autonomy_ceiling):
        requirements.append(
            ApprovalRequirement(
                requirement="operator",
                reason="Risk tier exceeds effective autonomy ceiling (constitution/local merge).",
                details={
                    "action": action,
                    "risk_tier": risk_tier.value,
                    "autonomy_ceiling": effective.autonomy_ceiling.value,
                    "constitution": effective.constitution_version,
                },
            )
        )

    if requirements:
        return ExecutionPlan(
            decision=Decision.needs_approval,
            authorization_decision=AuthorizationDecision.allow,
            approval_state=ApprovalState.pending,
            rationale="Approval requirements not satisfied.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=requirements,
            steps=[],
            capability_id=cap_id,
            tool_id=tool_id,
        )

    if action == StewardActions.DRAFT_APPROVE:
        steps.append(
            ExecutionStep(
                step=1,
                type="openshell.approve_draft_chunk",
                description="Approve one pending draft chunk.",
                payload={"sandbox_name": sandbox_name, "chunk_id": chunk_id},
            )
        )
        return ExecutionPlan(
            decision=Decision.allow,
            authorization_decision=AuthorizationDecision.allow,
            approval_state=ApprovalState.approved,
            rationale="Approved by operator.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=steps,
            capability_id=cap_id,
            tool_id=tool_id,
        )

    if action == StewardActions.DRAFT_REJECT:
        steps.append(
            ExecutionStep(
                step=1,
                type="openshell.reject_draft_chunk",
                description="Reject one pending draft chunk.",
                payload={
                    "sandbox_name": sandbox_name,
                    "chunk_id": chunk_id,
                    "reason": proposal.parameters.get("reason", ""),
                },
            )
        )
        return ExecutionPlan(
            decision=Decision.allow,
            authorization_decision=AuthorizationDecision.allow,
            approval_state=ApprovalState.approved,
            rationale="Rejected by operator.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=steps,
            capability_id=cap_id,
            tool_id=tool_id,
        )

    if action == StewardActions.DRAFT_EDIT:
        proposed_rule = proposal.parameters.get("proposed_rule")
        if not isinstance(proposed_rule, dict):
            return ExecutionPlan(
                decision=Decision.deny,
                authorization_decision=AuthorizationDecision.deny,
                approval_state=ApprovalState.not_required,
                rationale="Missing parameters.proposed_rule (object).",
                risk_tier=risk_tier,
                approval_policy=approval_policy,
                requirements=[],
                steps=[],
                capability_id=cap_id,
                tool_id=tool_id,
            )
        steps.append(
            ExecutionStep(
                step=1,
                type="openshell.edit_draft_chunk",
                description="Edit one pending draft chunk in-place.",
                payload={"sandbox_name": sandbox_name, "chunk_id": chunk_id, "proposed_rule": proposed_rule},
            )
        )
        return ExecutionPlan(
            decision=Decision.allow,
            authorization_decision=AuthorizationDecision.allow,
            approval_state=ApprovalState.approved,
            rationale="Edited by operator.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=steps,
            capability_id=cap_id,
            tool_id=tool_id,
        )

    if action == StewardActions.DRAFT_APPROVE_ALL:
        include_security_flagged = bool(proposal.parameters.get("include_security_flagged", False))
        steps.append(
            ExecutionStep(
                step=1,
                type="openshell.approve_all_draft_chunks",
                description="Approve all pending chunks (optionally include security-flagged).",
                payload={
                    "sandbox_name": sandbox_name,
                    "include_security_flagged": include_security_flagged,
                },
            )
        )
        return ExecutionPlan(
            decision=Decision.allow,
            authorization_decision=AuthorizationDecision.allow,
            approval_state=ApprovalState.approved,
            rationale="Approved all by operator.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=steps,
            capability_id=cap_id,
            tool_id=tool_id,
        )

    if action == StewardActions.DRAFT_CLEAR:
        steps.append(
            ExecutionStep(
                step=1,
                type="openshell.clear_draft_chunks",
                description="Clear all pending draft chunks for sandbox.",
                payload={"sandbox_name": sandbox_name},
            )
        )
        return ExecutionPlan(
            decision=Decision.allow,
            authorization_decision=AuthorizationDecision.allow,
            approval_state=ApprovalState.approved,
            rationale="Cleared by operator.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=steps,
            capability_id=cap_id,
            tool_id=tool_id,
        )

    if action == StewardActions.DRAFT_APPROVE_MATCHING:
        match = proposal.parameters.get("match") if isinstance(proposal.parameters, dict) else None
        if not isinstance(match, dict):
            return ExecutionPlan(
                decision=Decision.deny,
                authorization_decision=AuthorizationDecision.deny,
                approval_state=ApprovalState.not_required,
                rationale="Missing parameters.match for approve_matching.",
                risk_tier=risk_tier,
                approval_policy=approval_policy,
                requirements=[],
                steps=[],
                capability_id=cap_id,
                tool_id=tool_id,
            )
        host = str(match.get("host", "")).strip()
        port = int(match.get("port", 0) or 0)
        binary_path = str(match.get("binary_path", "")).strip()
        if not host or port <= 0 or not binary_path:
            return ExecutionPlan(
                decision=Decision.deny,
                authorization_decision=AuthorizationDecision.deny,
                approval_state=ApprovalState.not_required,
                rationale="parameters.match must include host, port, and binary_path.",
                risk_tier=risk_tier,
                approval_policy=approval_policy,
                requirements=[],
                steps=[],
                capability_id=cap_id,
                tool_id=tool_id,
            )

        steps.append(
            ExecutionStep(
                step=1,
                type="openshell.approve_matching_draft_chunk",
                description="Approve a pending draft chunk that matches host/port/binary.",
                payload={
                    "sandbox_name": sandbox_name,
                    "match": {"host": host, "port": port, "binary_path": binary_path},
                },
            )
        )
        return ExecutionPlan(
            decision=Decision.allow,
            authorization_decision=AuthorizationDecision.allow,
            approval_state=ApprovalState.approved,
            rationale="Approved matching draft chunk by operator.",
            risk_tier=risk_tier,
            approval_policy=approval_policy,
            requirements=[],
            steps=steps,
            capability_id=cap_id,
            tool_id=tool_id,
        )

    return ExecutionPlan(
        decision=Decision.deny,
        authorization_decision=AuthorizationDecision.deny,
        approval_state=ApprovalState.not_required,
        rationale="Unsupported draft policy action.",
        risk_tier=risk_tier,
        approval_policy=approval_policy,
        requirements=[],
        steps=[],
        capability_id=cap_id,
        tool_id=tool_id,
    )


def _find_chunk(openshell: OpenShellClient, *, sandbox_name: str, chunk_id: str) -> Optional[DraftPolicyChunk]:
    draft = openshell.get_draft_policy(sandbox_name=sandbox_name, status_filter="")
    for chunk in draft.chunks:
        if chunk.id == chunk_id:
            return chunk
    return None


def execute_plan(openshell: OpenShellClient, plan: ExecutionPlan) -> Tuple[bool, Dict[str, Any]]:
    if plan.decision != Decision.allow:
        return False, {"error": "not_allowed", "decision": plan.decision}
    if not plan.steps:
        return True, {"ok": True, "result": "noop"}

    results: List[Dict[str, Any]] = []
    for step in plan.steps:
        try:
            t = step.type
            p = step.payload
            if t == "openshell.get_draft_policy":
                dp = openshell.get_draft_policy(
                    sandbox_name=str(p["sandbox_name"]),
                    status_filter=str(p.get("status_filter", "")),
                )
                results.append(
                    {
                        "ok": True,
                        "draft_version": dp.draft_version,
                        "chunks": [c.__dict__ for c in dp.chunks],
                    }
                )
            elif t == "openshell.approve_draft_chunk":
                results.append(
                    openshell.approve_draft_chunk(
                        sandbox_name=str(p["sandbox_name"]),
                        chunk_id=str(p["chunk_id"]),
                    )
                )
            elif t == "openshell.approve_matching_draft_chunk":
                m = p.get("match") if isinstance(p, dict) else None
                m = m if isinstance(m, dict) else {}
                host = str(m.get("host", "")).strip()
                port = int(m.get("port", 0) or 0)
                binary_path = str(m.get("binary_path", "")).strip()
                dp = openshell.get_draft_policy(sandbox_name=str(p["sandbox_name"]))
                found: Optional[DraftPolicyChunk] = None
                for c in dp.chunks:
                    if str(c.status).lower() != "pending":
                        continue
                    eps = (c.proposed_rule or {}).get("endpoints", []) if isinstance(c.proposed_rule, dict) else []
                    bins = (c.proposed_rule or {}).get("binaries", []) if isinstance(c.proposed_rule, dict) else []
                    if not isinstance(eps, list) or not isinstance(bins, list):
                        continue
                    ep_ok = any(
                        isinstance(e, dict)
                        and str(e.get("host", "")).strip() == host
                        and int(e.get("port", 0) or 0) == port
                        for e in eps
                    )
                    bin_ok = any(
                        isinstance(b, dict) and str(b.get("path", "")).strip() == binary_path for b in bins
                    )
                    if ep_ok and bin_ok:
                        found = c
                        break
                if not found:
                    results.append({"ok": False, "error": "chunk_not_found", "match": m})
                else:
                    results.append(
                        openshell.approve_draft_chunk(
                            sandbox_name=str(p["sandbox_name"]),
                            chunk_id=str(found.id),
                        )
                    )
            elif t == "openshell.reject_draft_chunk":
                results.append(
                    openshell.reject_draft_chunk(
                        sandbox_name=str(p["sandbox_name"]),
                        chunk_id=str(p["chunk_id"]),
                        reason=str(p.get("reason", "")),
                    )
                )
            elif t == "openshell.edit_draft_chunk":
                results.append(
                    openshell.edit_draft_chunk(
                        sandbox_name=str(p["sandbox_name"]),
                        chunk_id=str(p["chunk_id"]),
                        proposed_rule=dict(p["proposed_rule"]),
                    )
                )
            elif t == "openshell.approve_all_draft_chunks":
                results.append(
                    openshell.approve_all_draft_chunks(
                        sandbox_name=str(p["sandbox_name"]),
                        include_security_flagged=bool(p.get("include_security_flagged", False)),
                    )
                )
            elif t == "openshell.clear_draft_chunks":
                results.append(openshell.clear_draft_chunks(sandbox_name=str(p["sandbox_name"])))
            else:
                results.append({"ok": False, "error": "unknown_step", "type": t})
        except Exception as exc:
            if isinstance(exc, grpc.RpcError):
                code = getattr(exc, "code", lambda: None)()
                details = getattr(exc, "details", lambda: None)()
                return False, {
                    "ok": False,
                    "error": "external_call_failed",
                    "step_type": step.type,
                    "grpc_code": str(code),
                    "grpc_details": details,
                    "message": str(exc),
                    "exception_type": type(exc).__name__,
                }
            return False, {
                "ok": False,
                "error": "external_call_failed",
                "step_type": step.type,
                "message": str(exc),
                "exception_type": type(exc).__name__,
            }

    return True, {"ok": True, "steps": results}


def generated_external_refs(proposal: Proposal, plan: ExecutionPlan) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    sandbox_name = str(proposal.parameters.get("sandbox_name", "")).strip()
    if sandbox_name:
        refs.append({"type": "sandbox_name", "value": sandbox_name})
    chunk_id = str(proposal.parameters.get("chunk_id", "")).strip()
    if chunk_id:
        refs.append({"type": "chunk_id", "value": chunk_id})
    for step in plan.steps:
        if step.type.startswith("openshell."):
            refs.append({"type": "openshell_operation", "value": step.type})
    # de-dupe (stable)
    seen = set()
    out: List[Dict[str, Any]] = []
    for r in refs:
        key = (r.get("type"), r.get("value"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out

