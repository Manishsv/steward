"""SQLite-backed stores sharing one connection (WAL, serialized writes)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from ..domain import (
    ApprovalRequestRecord,
    AuditRecord,
    CandidateActionSetRecord,
    DecisionRecord,
    ExecutionRecord,
    GovernanceProposalRecord,
    InstitutionalDecisionRecord,
)
from .serialize import (
    approval_request_from_dict,
    approval_request_to_dict,
    audit_record_from_dict,
    audit_record_to_dict,
    candidate_set_from_dict,
    candidate_set_to_dict,
    decision_record_from_dict,
    decision_record_to_dict,
    execution_record_from_dict,
    execution_record_to_dict,
    governance_proposal_from_dict,
    governance_proposal_to_dict,
    institution_record_from_dict,
    institution_record_to_dict,
)


class SqliteConnection:
    """Single connection with a lock; suitable for FastAPI dev/single-worker."""

    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS audits (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY,
                content_proposal_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_proposals_content ON proposals(content_proposal_id);
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS candidate_sets (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS institution_decisions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def query_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            row = cur.fetchone()
            return row

    def query_all(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return list(cur.fetchall())


class SqliteAuditStore:
    def __init__(self, db: SqliteConnection) -> None:
        self._db = db

    def new_id(self) -> str:
        return str(uuid4())

    def put(self, record: AuditRecord) -> None:
        payload = json.dumps(audit_record_to_dict(record), separators=(",", ":"))
        self._db.execute(
            "INSERT OR REPLACE INTO audits (id, created_at, payload) VALUES (?,?,?)",
            (record.id, record.created_at.isoformat(), payload),
        )

    def get(self, audit_id: str) -> Optional[AuditRecord]:
        row = self._db.query_one("SELECT payload FROM audits WHERE id = ?", (audit_id,))
        if row is None:
            return None
        return audit_record_from_dict(json.loads(row[0]))

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)


class SqliteProposalStore:
    def __init__(self, db: SqliteConnection) -> None:
        self._db = db

    def new_id(self) -> str:
        return str(uuid4())

    def put(self, record: GovernanceProposalRecord) -> None:
        payload = json.dumps(governance_proposal_to_dict(record), separators=(",", ":"))
        cid = record.proposal.proposal_id
        self._db.execute(
            """INSERT OR REPLACE INTO proposals
               (id, content_proposal_id, created_at, updated_at, payload) VALUES (?,?,?,?,?)""",
            (
                record.id,
                cid,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                payload,
            ),
        )

    def get(self, proposal_id: str) -> Optional[GovernanceProposalRecord]:
        row = self._db.query_one("SELECT payload FROM proposals WHERE id = ?", (proposal_id,))
        if row is None:
            return None
        return governance_proposal_from_dict(json.loads(row[0]))

    def find_by_content_proposal_id(self, content_proposal_id: str) -> List[GovernanceProposalRecord]:
        rows = self._db.query_all(
            "SELECT payload FROM proposals WHERE content_proposal_id = ?", (content_proposal_id,)
        )
        return [governance_proposal_from_dict(json.loads(r[0])) for r in rows]

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)


class SqliteDecisionStore:
    def __init__(self, db: SqliteConnection) -> None:
        self._db = db

    def new_id(self) -> str:
        return str(uuid4())

    def put(self, record: DecisionRecord) -> None:
        payload = json.dumps(decision_record_to_dict(record), separators=(",", ":"))
        self._db.execute(
            "INSERT OR REPLACE INTO decisions (id, created_at, payload) VALUES (?,?,?)",
            (record.id, record.created_at.isoformat(), payload),
        )

    def get(self, record_id: str) -> Optional[DecisionRecord]:
        row = self._db.query_one("SELECT payload FROM decisions WHERE id = ?", (record_id,))
        if row is None:
            return None
        return decision_record_from_dict(json.loads(row[0]))

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)


class SqliteExecutionStore:
    def __init__(self, db: SqliteConnection) -> None:
        self._db = db

    def new_id(self) -> str:
        return str(uuid4())

    def put(self, record: ExecutionRecord) -> None:
        payload = json.dumps(execution_record_to_dict(record), separators=(",", ":"))
        self._db.execute(
            "INSERT OR REPLACE INTO executions (id, created_at, payload) VALUES (?,?,?)",
            (record.id, record.created_at.isoformat(), payload),
        )

    def get(self, record_id: str) -> Optional[ExecutionRecord]:
        row = self._db.query_one("SELECT payload FROM executions WHERE id = ?", (record_id,))
        if row is None:
            return None
        return execution_record_from_dict(json.loads(row[0]))

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)


class SqliteApprovalStore:
    def __init__(self, db: SqliteConnection) -> None:
        self._db = db

    def new_id(self) -> str:
        return str(uuid4())

    def put(self, record: ApprovalRequestRecord) -> None:
        payload = json.dumps(approval_request_to_dict(record), separators=(",", ":"))
        self._db.execute(
            """INSERT OR REPLACE INTO approvals
               (id, created_at, updated_at, payload) VALUES (?,?,?,?)""",
            (
                record.id,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                payload,
            ),
        )

    def get(self, record_id: str) -> Optional[ApprovalRequestRecord]:
        row = self._db.query_one("SELECT payload FROM approvals WHERE id = ?", (record_id,))
        if row is None:
            return None
        return approval_request_from_dict(json.loads(row[0]))

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)


class SqliteCandidateSetStore:
    def __init__(self, db: SqliteConnection) -> None:
        self._db = db

    def new_id(self) -> str:
        return str(uuid4())

    def put(self, record: CandidateActionSetRecord) -> None:
        payload = json.dumps(candidate_set_to_dict(record), separators=(",", ":"))
        self._db.execute(
            """INSERT OR REPLACE INTO candidate_sets
               (id, created_at, updated_at, payload) VALUES (?,?,?,?)""",
            (
                record.id,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                payload,
            ),
        )

    def get(self, record_id: str) -> Optional[CandidateActionSetRecord]:
        row = self._db.query_one("SELECT payload FROM candidate_sets WHERE id = ?", (record_id,))
        if row is None:
            return None
        return candidate_set_from_dict(json.loads(row[0]))

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)


class SqliteInstitutionStore:
    def __init__(self, db: SqliteConnection) -> None:
        self._db = db

    def new_id(self) -> str:
        return str(uuid4())

    def put(self, record: InstitutionalDecisionRecord) -> None:
        payload = json.dumps(institution_record_to_dict(record), separators=(",", ":"))
        self._db.execute(
            "INSERT OR REPLACE INTO institution_decisions (id, created_at, payload) VALUES (?,?,?)",
            (record.id, record.created_at.isoformat(), payload),
        )

    def get(self, record_id: str) -> Optional[InstitutionalDecisionRecord]:
        row = self._db.query_one(
            "SELECT payload FROM institution_decisions WHERE id = ?", (record_id,)
        )
        if row is None:
            return None
        return institution_record_from_dict(json.loads(row[0]))

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
