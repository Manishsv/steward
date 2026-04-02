from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional
from uuid import uuid4

from .domain import GovernanceProposalRecord


class InMemoryProposalStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._records: Dict[str, GovernanceProposalRecord] = {}

    def new_id(self) -> str:
        return str(uuid4())

    def put(self, record: GovernanceProposalRecord) -> None:
        with self._lock:
            self._records[record.id] = record

    def get(self, proposal_id: str) -> Optional[GovernanceProposalRecord]:
        with self._lock:
            return self._records.get(proposal_id)

    def find_by_content_proposal_id(self, content_proposal_id: str) -> List[GovernanceProposalRecord]:
        """Match GovernanceProposalRecord.proposal.proposal_id (stable content hash)."""
        with self._lock:
            return [r for r in self._records.values() if r.proposal.proposal_id == content_proposal_id]

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
