from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Optional
from uuid import uuid4

from .domain import CandidateActionSetRecord


class InMemoryCandidateSetStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._records: Dict[str, CandidateActionSetRecord] = {}

    def new_id(self) -> str:
        return str(uuid4())

    def put(self, record: CandidateActionSetRecord) -> None:
        with self._lock:
            self._records[record.id] = record

    def get(self, record_id: str) -> Optional[CandidateActionSetRecord]:
        with self._lock:
            return self._records.get(record_id)

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
