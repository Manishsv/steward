from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

from .domain import AuditRecord


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._records: Dict[str, AuditRecord] = {}

    def new_id(self) -> str:
        return str(uuid4())

    def put(self, record: AuditRecord) -> None:
        with self._lock:
            self._records[record.id] = record

    def get(self, audit_id: str) -> Optional[AuditRecord]:
        with self._lock:
            return self._records.get(audit_id)

    @staticmethod
    def to_public_payload(record: AuditRecord) -> Dict[str, Any]:
        """
        Convert internal AuditRecord to the existing API's AuditRecord.payload shape.
        """
        payload: Dict[str, Any] = {}
        if record.plan is not None:
            payload["plan"] = {
                "decision": record.plan.decision.value,
                "rationale": record.plan.rationale,
                "risk_tier": record.plan.risk_tier.value,
                "approval_policy": asdict(record.plan.approval_policy) if record.plan.approval_policy else None,
                "requirements": [asdict(r) for r in record.plan.requirements],
                "steps": [asdict(s) for s in record.plan.steps],
            }
        if record.result:
            payload["result"] = record.result

        payload["audit"] = {
            "proposal_id": record.proposal_id,
            "action_type": record.action_type.value,
            "requested_by": record.requested_by.to_public() if record.requested_by else None,
            "approved_by": record.approved_by.to_public() if record.approved_by else None,
            "approval_status": record.approval_status,
            "governance_basis": list(record.governance_basis),
            "external_refs": list(record.external_refs),
        }
        if record.governance_proposal_id:
            payload["audit"]["governance_proposal_id"] = record.governance_proposal_id
        if record.decision_record_id:
            payload["audit"]["decision_record_id"] = record.decision_record_id
        if record.execution_record_id:
            payload["audit"]["execution_record_id"] = record.execution_record_id
        return payload

    @staticmethod
    def now() -> datetime:
        from datetime import timezone

        return datetime.now(timezone.utc)
