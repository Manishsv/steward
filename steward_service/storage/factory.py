"""Construct storage bundle (in-memory default, optional SQLite)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from ..approval_store import InMemoryApprovalStore
from ..audit_store import InMemoryAuditStore
from ..candidate_set_store import InMemoryCandidateSetStore
from ..decision_store import InMemoryDecisionStore
from ..execution_store import InMemoryExecutionStore
from ..institution_store import InMemoryInstitutionDecisionStore
from ..proposal_store import InMemoryProposalStore
from .sqlite_backend import (
    SqliteApprovalStore,
    SqliteAuditStore,
    SqliteCandidateSetStore,
    SqliteConnection,
    SqliteDecisionStore,
    SqliteExecutionStore,
    SqliteInstitutionStore,
    SqliteProposalStore,
)


@dataclass(frozen=True)
class StorageBundle:
    audit: object
    proposals: object
    decisions: object
    executions: object
    approvals: object
    candidate_sets: object
    institution: object
    backend: str
    sqlite_path: Optional[str] = None


def build_storage_bundle() -> StorageBundle:
    """
    STEWARD_STORAGE_BACKEND=memory (default) | sqlite
    STEWARD_SQLITE_PATH=path/to/steward.db (required for sqlite)
    """
    backend = os.environ.get("STEWARD_STORAGE_BACKEND", "memory").strip().lower()
    if backend == "sqlite":
        path = os.environ.get("STEWARD_SQLITE_PATH", "").strip()
        if not path:
            raise ValueError(
                "STEWARD_SQLITE_PATH must be set when STEWARD_STORAGE_BACKEND=sqlite"
            )
        conn = SqliteConnection(path)
        return StorageBundle(
            audit=SqliteAuditStore(conn),
            proposals=SqliteProposalStore(conn),
            decisions=SqliteDecisionStore(conn),
            executions=SqliteExecutionStore(conn),
            approvals=SqliteApprovalStore(conn),
            candidate_sets=SqliteCandidateSetStore(conn),
            institution=SqliteInstitutionStore(conn),
            backend="sqlite",
            sqlite_path=path,
        )
    return StorageBundle(
        audit=InMemoryAuditStore(),
        proposals=InMemoryProposalStore(),
        decisions=InMemoryDecisionStore(),
        executions=InMemoryExecutionStore(),
        approvals=InMemoryApprovalStore(),
        candidate_sets=InMemoryCandidateSetStore(),
        institution=InMemoryInstitutionDecisionStore(),
        backend="memory",
        sqlite_path=None,
    )


def build_storage_bundle_for_tests_sqlite(path: str) -> StorageBundle:
    """Explicit SQLite bundle (tests); does not read environment variables."""
    conn = SqliteConnection(path)
    return StorageBundle(
        audit=SqliteAuditStore(conn),
        proposals=SqliteProposalStore(conn),
        decisions=SqliteDecisionStore(conn),
        executions=SqliteExecutionStore(conn),
        approvals=SqliteApprovalStore(conn),
        candidate_sets=SqliteCandidateSetStore(conn),
        institution=SqliteInstitutionStore(conn),
        backend="sqlite",
        sqlite_path=path,
    )
