from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, List, Optional, Tuple

from .domain import Decision, ExecutionPlan, GovernanceProposalRecord, Proposal, ProposalLifecycleState
from .proposal_store import InMemoryProposalStore


def _utc_now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)


def create_draft(
    store: InMemoryProposalStore,
    content: Proposal,
) -> GovernanceProposalRecord:
    now = store.now()
    rec = GovernanceProposalRecord(
        id=store.new_id(),
        created_at=now,
        updated_at=now,
        state=ProposalLifecycleState.draft,
        proposal=content,
    )
    store.put(rec)
    return rec


def submit(store: InMemoryProposalStore, record: GovernanceProposalRecord) -> GovernanceProposalRecord:
    if record.state != ProposalLifecycleState.draft:
        return record
    record.state = ProposalLifecycleState.submitted
    record.updated_at = store.now()
    store.put(record)
    return record


def apply_evaluation(
    store: InMemoryProposalStore,
    record: GovernanceProposalRecord,
    plan: ExecutionPlan,
) -> GovernanceProposalRecord:
    """
    After build_execution_plan: transition submitted -> evaluated -> terminal governance branch.
    """
    record.plan = plan
    record.governance_decision = plan.decision
    record.governance_rationale = plan.rationale
    record.updated_at = store.now()

    if record.state == ProposalLifecycleState.draft:
        record.state = ProposalLifecycleState.submitted

    record.state = ProposalLifecycleState.evaluated
    d = plan.decision
    if d == Decision.deny:
        record.state = ProposalLifecycleState.denied
    elif d == Decision.needs_approval:
        record.state = ProposalLifecycleState.approval_pending
    elif d == Decision.allow:
        record.state = ProposalLifecycleState.approved

    store.put(record)
    return record


def mark_executing(store: InMemoryProposalStore, record: GovernanceProposalRecord) -> GovernanceProposalRecord:
    record.state = ProposalLifecycleState.executing
    record.updated_at = store.now()
    store.put(record)
    return record


def mark_executed(
    store: InMemoryProposalStore,
    record: GovernanceProposalRecord,
    result: dict,
    *,
    ok: bool,
) -> GovernanceProposalRecord:
    record.execution_result = result
    record.updated_at = store.now()
    if ok:
        record.state = ProposalLifecycleState.executed
    else:
        record.state = ProposalLifecycleState.execution_failed
    store.put(record)
    return record


def link_audit(record: GovernanceProposalRecord, audit_id: str) -> None:
    if audit_id not in record.linked_audit_ids:
        record.linked_audit_ids.append(audit_id)


def mark_proposal_approved_after_external_ok(store: InMemoryProposalStore, gp_id: str) -> None:
    """Transition approval_pending -> approved when a valid ApprovalRequest is satisfied."""
    gp = store.get(gp_id)
    if gp and gp.state == ProposalLifecycleState.approval_pending:
        gp.state = ProposalLifecycleState.approved
        gp.updated_at = store.now()
        store.put(gp)


def mark_proposal_denied_after_approval_rejection(store: InMemoryProposalStore, gp_id: str) -> None:
    """Transition approval_pending -> denied when an ApprovalRequest is rejected."""
    gp = store.get(gp_id)
    if gp and gp.state == ProposalLifecycleState.approval_pending:
        gp.state = ProposalLifecycleState.denied
        gp.updated_at = store.now()
        store.put(gp)


def evaluate_content(
    store: InMemoryProposalStore,
    content: Proposal,
    plan_builder: Callable[[Proposal], ExecutionPlan],
    *,
    start_from_draft: bool = True,
) -> Tuple[GovernanceProposalRecord, ExecutionPlan]:
    """
    Create (draft), submit, evaluate in one step for compatibility wrappers.
    """
    rec = create_draft(store, content)
    if start_from_draft:
        submit(store, rec)
    plan = plan_builder(content)
    apply_evaluation(store, rec, plan)
    return rec, plan
